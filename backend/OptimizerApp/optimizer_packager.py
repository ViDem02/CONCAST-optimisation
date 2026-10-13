"""
Optimizer packager: bridge between the database and the optimizers.

This module does not optimize anything itself. It packages the data of an
Optimization (production plan, generation and prices) into an
OptimizationProblem following simulator.m, hands it to the optimizer selected
in the Optimization object (see OptimizerApp.optimizers), and unpacks the
returned shifts into an optimized production plan and cost metrics:
1. Checks that generation and prices cover every hour of the week (DatasetApp.series)
   and retimes them to 5-minute timesteps
2. Builds production timetable matrix (nPhases x N) where each row is a phase activity
3. Expands phases to independent runs (contiguous activity periods; the week is
   periodic, so a run crossing Sunday 24:00 is one run)
4. Runs the selected optimizer ("milp" or "from-scratch")
5. Checks that the optimised schedule uses exactly the energy of the original one
6. Creates optimized production plan with shifted schedules

Matrix orientation (following simulator.m):
- phase_active: nPhases x N (each row is a phase-run, each column is a timestep)
- elec_demand_matrix: nPhases x N (electricity demand per phase-run per timestep)
- total_demand: N-length vector (sum across phases for each timestep)

This approach closely mirrors simulator.m for consistency and correctness.
"""

from datetime import datetime, timedelta
import pytz
import numpy as np
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from DatasetApp.series import five_minute_grid, hourly_values, to_steps
from .optimizers import OptimizationProblem, get_optimizer
from .optimizers.base import apply_shifts_from_steps, compute_cost, run_steps


TIMESTEP_MINUTES = 5  # 5-minute timesteps


def detect_shift_runs(activity_vector):
    """
    Detect contiguous runs of 1s in a binary activity vector of the periodic week.
    Each run represents a separate shift that can be optimized independently.

    A run that is active both at the last and at the first step continues across
    Sunday 24:00: it is returned once, as (start, end) with end >= len(activity_vector)
    (see optimizers.base.run_steps).

    Args:
        activity_vector: List/array of 0s and 1s

    Returns:
        List of tuples (start_index, end_index) for each run
    """
    runs = []
    in_run = False
    start_idx = 0

    for i, val in enumerate(activity_vector):
        if val > 0.5 and not in_run:
            # Start of new run
            start_idx = i
            in_run = True
        elif val <= 0.5 and in_run:
            # End of run
            runs.append((start_idx, i - 1))
            in_run = False

    # Handle case where last run extends to end
    if in_run:
        runs.append((start_idx, len(activity_vector) - 1))

    # Periodic week: the run at the end continues with the run at the start
    N = len(activity_vector)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == N - 1:
        first = runs.pop(0)
        last = runs.pop()
        runs.append((last[0], first[1] + N))

    return runs


def build_production_matrix(production_plan, timesteps):
    """
    Build production matrix (like simulator.m): one row per process, one column per timestep.

    Each process gets one row initially; expand_phases_to_runs later splits it
    into its runs. The allowed movement is read from the shifts, per timestep,
    so that every run can take the tolerance of the shift it comes from.

    Returns:
        Tuple of (phase_active, phase_info, forward_steps, backward_steps) where:
        - phase_active: numpy array of shape (nPhases, N) with binary activity
        - phase_info: list of dicts with process info for each phase
        - forward_steps, backward_steps: (nPhases, N) int arrays, allowed delay /
          advance in steps of the shifts active at each timestep (smallest one
          when shifts touch)
    """
    from SimulationApp.simulation import minutes_of_week, shift_activity
    
    processes = list(production_plan.processes.prefetch_related('shifts'))
    nPhases = len(processes)
    N = len(timesteps)
    week_minutes = minutes_of_week(timesteps)
    
    phase_active = np.zeros((nPhases, N))
    forward_steps = np.full((nPhases, N), np.iinfo(np.int64).max, dtype=np.int64)
    backward_steps = np.full((nPhases, N), np.iinfo(np.int64).max, dtype=np.int64)
    phase_info = []
    
    for phase_idx, process in enumerate(processes):
        for shift in process.shifts.all():
            active = shift_activity(week_minutes, shift)
            phase_active[phase_idx, active] = 1
            forward_steps[phase_idx, active] = np.minimum(
                forward_steps[phase_idx, active], shift.max_forward_minutes // TIMESTEP_MINUTES)
            backward_steps[phase_idx, active] = np.minimum(
                backward_steps[phase_idx, active], shift.max_backwards_minutes // TIMESTEP_MINUTES)
        
        phase_info.append({
            'process_id': process.id,
            'process_name': process.name,
            'electricity_consumption_kWh': process.electricity_consumption_kWh,
        })
    
    return phase_active, phase_info, forward_steps, backward_steps


def expand_phases_to_runs(phase_active, phase_info, forward_steps, backward_steps):
    """
    Expand phases to multiple runs (like simulator.m does).
    Each contiguous run of activity becomes an independent optimizable unit.
    
    Args:
        phase_active: nPhases x N binary matrix
        phase_info: list of phase information dicts
        forward_steps, backward_steps: nPhases x N allowed delay / advance (see build_production_matrix)
    
    Returns:
        Tuple of (expanded_active, expanded_info, expanded_names) where:
        - expanded_active: nRuns x N binary matrix
        - expanded_info: list of run information dicts
        - expanded_names: list of run names (e.g., 'process_name_run1')
    """
    nPhases, N = phase_active.shape
    
    expanded_active = []
    expanded_info = []
    expanded_names = []
    
    for phase_idx in range(nPhases):
        activity = phase_active[phase_idx, :]
        runs = detect_shift_runs(activity)
        info = phase_info[phase_idx]
        
        if len(runs) == 0:
            continue
        
        for run_idx, (start, end) in enumerate(runs):
            # Create activity vector for this run (wrapping past Sunday 24:00 if needed)
            steps = np.arange(start, end + 1) % N
            run_activity = np.zeros(N)
            run_activity[steps] = 1
            expanded_active.append(run_activity)
            
            # Create info for this run
            run_name = f"{info['process_name']}_run{run_idx + 1}"
            expanded_names.append(run_name)
            
            expanded_info.append({
                'process_id': info['process_id'],
                'process_name': info['process_name'],
                'run_name': run_name,
                'run_number': run_idx + 1,
                'electricity_consumption_kWh': info['electricity_consumption_kWh'],
                'original_start': start,
                'original_end': end,
                'max_forward_steps': int(forward_steps[phase_idx, steps].min()),
                'max_backward_steps': int(backward_steps[phase_idx, steps].min())
            })
    
    # Stack into matrix: nRuns x N
    if expanded_active:
        expanded_active = np.vstack(expanded_active)
    else:
        expanded_active = np.zeros((0, N))
    
    return expanded_active, expanded_info, expanded_names


STEPS = ['Checking the data', 'Building the model', 'Searching for the cheapest timetable',
         'Writing the optimised plan']


def run_optimization(optimization_id, progress=None):
    """
    Run the full optimization for an Optimization object, using the
    optimizer selected in its `optimizer` field.
    
    Args:
        progress: optional callable progress(step, detail='', time_limit=None), called when each of
            the STEPS (numbered from 1) starts; see OptimizerApp.background
    
    Returns:
        Updated Optimization object with results
    """
    report = progress or (lambda step, detail='', time_limit=None: None)
    # Import models here to avoid circular imports
    from PlanningApp.models import WeeklyProductionPlan, Process, Shift
    from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
    from .models import Optimization
    
    optimization = Optimization.objects.get(id=optimization_id)
    optimizer = get_optimizer(optimization.optimizer)
    if (optimization.reference_week_end - optimization.reference_week_start).days != 6:
        raise ValueError("The reference period must be exactly one week (7 days), "
                         "otherwise the optimised weekly plan would miss or repeat shifts")
    
    # Get datasets from optimization object
    generation_dataset = optimization.generation_dataset
    prices_dataset = optimization.prices_dataset
    
    if not generation_dataset or not prices_dataset:
        raise ValueError("Generation and prices datasets must be specified in the optimization")
    
    # Get reference week time range
    tz = pytz.timezone(settings.TIME_ZONE)
    start_time = tz.localize(datetime.combine(optimization.reference_week_start, datetime.min.time()))
    end_time = tz.localize(datetime.combine(optimization.reference_week_end, datetime.max.time()))
    
    report(1, 'Generation and prices of every hour of the week')
    # Every hour of the week must have finite, non-negative generation and prices:
    # a missing hour must never be read as zero (free electricity)
    generation = hourly_values(
        GenerationRecord.objects.filter(generation_dataset=generation_dataset),
        ['ele_generated_by_solar_kWh', 'ele_generated_by_cogen_kWh'],
        start_time, end_time, f'generation data "{generation_dataset.name}"')
    prices = hourly_values(
        PricesRecord.objects.filter(prices_dataset=prices_dataset), ['electricity_price'],
        start_time, end_time, f'electricity prices "{prices_dataset.name}"')
    
    # Build 5-minute timestep vector
    timesteps = five_minute_grid(start_time, end_time)
    N = len(timesteps)
    dt_h = TIMESTEP_MINUTES / 60.0  # Hours per step
    
    report(2, 'Runs of the production plan and their allowed positions')
    # Build production matrix: nPhases x N (following simulator.m approach)
    phase_active, phase_info, forward_steps, backward_steps = build_production_matrix(
        optimization.reference_production_plan,
        timesteps
    )
    
    # Expand to multiple runs per phase (like simulator.m does)
    phase_active, phase_info, phase_names = expand_phases_to_runs(
        phase_active, phase_info, forward_steps, backward_steps)
    nPhases = len(phase_info)  # Total number of phase-runs
    
    if nPhases == 0:
        raise ValueError("No shifts found in reference production plan")
    
    # Build demand matrix: nPhases x N (following simulator.m)
    # Each row is the electricity demand for that phase-run at each timestep
    elec_demand_matrix = np.zeros((nPhases, N))
    for i, info in enumerate(phase_info):
        # Convert hourly kWh to kWh per 5-min step
        consumption_per_step = info['electricity_consumption_kWh'] * dt_h
        elec_demand_matrix[i, :] = phase_active[i, :] * consumption_per_step
    
    # Generation (kWh per step, interpolated within the hour) and prices (held within the hour)
    gen_kWh = (to_steps(generation, 0, timesteps, linear=True)
               + to_steps(generation, 1, timesteps, linear=True)) * dt_h
    price_el = to_steps(prices, 0, timesteps, linear=False)
    
    # Run the selected optimizer
    problem = OptimizationProblem(
        elec_demand_matrix=elec_demand_matrix,
        gen_kWh=gen_kWh,
        price_el=price_el,
        max_shift_steps=np.array([min(info['max_forward_steps'], info['max_backward_steps'])
                                  for info in phase_info], dtype=int),
        run_info=phase_info
    )
    positions = sum(i['max_backward_steps'] + i['max_forward_steps'] + 1 for i in phase_info)
    report(3, f'{nPhases} runs, {positions:,} possible positions ({optimizer.label})',
           time_limit=getattr(optimizer, 'time_limit', None))
    result = optimizer.optimize(problem)
    
    # Ensure the returned shifts are integers within the asymmetric bounds -B_r..F_r
    current_shifts = np.clip(
        np.asarray(result.shift_steps).round().astype(int),
        -np.array([info['max_backward_steps'] for info in phase_info]),
        np.array([info['max_forward_steps'] for info in phase_info])
    )
    
    # Baseline cost (no optimization)
    baseline_demand = elec_demand_matrix.sum(axis=0)  # Sum across phases
    baseline_cost, _ = compute_cost(baseline_demand, gen_kWh, price_el)
    
    # Final cost calculation
    final_shifted_demand = apply_shifts_from_steps(elec_demand_matrix, current_shifts)
    final_total_demand = final_shifted_demand.sum(axis=0)  # Sum across phases
    final_cost, final_details = compute_cost(final_total_demand, gen_kWh, price_el)
    
    # Safety net: moving shifts must never create or destroy energy
    baseline_energy, final_energy = float(baseline_demand.sum()), float(final_total_demand.sum())
    if not np.isclose(final_energy, baseline_energy, rtol=1e-9, atol=1e-6):
        raise RuntimeError(f'The optimised schedule uses {final_energy:.3f} kWh instead of '
                           f'{baseline_energy:.3f} kWh: it was not saved.')
    
    report(4, f'{int((current_shifts != 0).sum())} runs moved')
    # Create or update optimized production plan
    with transaction.atomic():
        existing_plan = optimization.optimized_production_plan
        if existing_plan:
            # Update existing optimized plan in-place: clear processes/shifts and reuse the plan
            # Optionally rename if a new name is provided
            if optimization.optimized_plan_name and existing_plan.name != optimization.optimized_plan_name:
                existing_plan.name = optimization.optimized_plan_name
                existing_plan.save(update_fields=["name"])

            # Remove previous content
            # Deleting processes will cascade delete their shifts
            existing_plan.processes.all().delete()
            optimized_plan = existing_plan
        else:
            # Use user-provided name or auto-generate
            plan_name = optimization.optimized_plan_name or f"{optimization.reference_production_plan.name}_optimized"
            optimized_plan = WeeklyProductionPlan.objects.create(
                name=plan_name,
                is_optimized=True
            )
        
        # Create processes and shifted shifts
        process_map = {}  # Map original process_id to new process
        
        for i, info in enumerate(phase_info):
            original_process_id = info['process_id']
            
            # Get or create process in optimized plan
            if original_process_id not in process_map:
                original_process = Process.objects.get(id=original_process_id)
                # Make process name unique by appending plan name
                unique_process_name = original_process.name
                new_process = Process.objects.create(
                    name=unique_process_name,
                    electricity_consumption_kWh=original_process.electricity_consumption_kWh,
                    production_plan=optimized_plan
                )
                process_map[original_process_id] = new_process
            
            # Get shift for this phase-run
            shift_minutes = int(current_shifts[i] * TIMESTEP_MINUTES)
            
            # New first step and first step after the run, around the periodic week:
            # a run moved past Sunday 24:00 continues on Monday 00:00 (and vice versa)
            new_start_step = (info['original_start'] + current_shifts[i]) % N
            new_end_step = (info['original_end'] + current_shifts[i] + 1) % N
            start_ts = timesteps[int(new_start_step)]
            end_ts = timesteps[int(new_end_step)]
            
            # Create shifted shift
            Shift.objects.create(
                name=f"{info['run_name']}",
                process=process_map[original_process_id],
                start_day=start_ts.weekday(),
                start_hour=start_ts.hour,
                start_minutes=start_ts.minute,
                end_day=end_ts.weekday(),
                end_hour=end_ts.hour,
                end_minutes=end_ts.minute,
                max_forward_minutes=info['max_forward_steps'] * TIMESTEP_MINUTES,
                max_backwards_minutes=info['max_backward_steps'] * TIMESTEP_MINUTES
            )
        
        # Update optimization object
        optimization.optimized_production_plan = optimized_plan
        # Round costs for stability and consistency with exporters/UX
        init_cost = float(baseline_cost)
        opt_cost = float(final_cost)
        savings_eur = max(0.0, init_cost - opt_cost)
        savings_pct = (savings_eur / init_cost) * 100.0 if init_cost > 0 else 0.0
        # Clamp to [0, 100] and round
        optimization.initial_cost_euros = round(init_cost, 2)
        optimization.optimized_cost_euros = round(opt_cost, 2)
        optimization.cost_savings_euros = round(savings_eur, 2)
        optimization.cost_savings_percent = round(max(0.0, min(100.0, savings_pct)), 2)
        optimization.completed_at = timezone.now()
        
        # Store detailed optimization data
        shift_changes = []
        for i, info in enumerate(phase_info):
            shift_changes.append({
                'phase_name': info['run_name'],
                'process_name': info['process_name'],
                'run_number': info['run_number'],
                'shift_minutes': int(current_shifts[i] * TIMESTEP_MINUTES),
                'shift_steps': int(current_shifts[i])
            })
        
        optimization.optimization_data = {
            'optimizer': optimizer.name,
            **result.data,  # Optimizer-specific diagnostics
            'baseline_cost': float(baseline_cost),
            'final_cost': float(final_cost),
            'total_wasted_energy': float(final_details['total_wasted']),
            'demand_kWh': {'original': baseline_energy, 'optimized': final_energy},
            'shift_changes': shift_changes,
            'num_timesteps': N,
            'num_runs_optimized': nPhases
        }
        
        # Only the result fields: the live progress is written concurrently by OptimizerApp.background
        optimization.save(update_fields=[
            'optimized_production_plan', 'initial_cost_euros', 'optimized_cost_euros', 'cost_savings_euros',
            'cost_savings_percent', 'completed_at', 'optimization_data'])
    
    return optimization
