"""
Optimizer packager: bridge between the database and the optimizers.

This module does not optimize anything itself. It packages the data of an
Optimization (production plan, generation and prices) into an
OptimizationProblem following simulator.m, hands it to the optimizer selected
in the Optimization object (see OptimizerApp.optimizers), and unpacks the
returned shifts into an optimized production plan and cost metrics:
1. Retimes hourly datasets to 5-minute timesteps
2. Builds production timetable matrix (nPhases x N) where each row is a phase activity
3. Expands phases to independent runs (contiguous activity periods)
4. Runs the selected optimizer ("milp" or "from-scratch")
5. Creates optimized production plan with shifted schedules

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

from .optimizers import OptimizationProblem, get_optimizer
from .optimizers.base import apply_shifts_from_steps, compute_cost


TIMESTEP_MINUTES = 5  # 5-minute timesteps


def retime_hourly_to_5min(hourly_data, start_time, end_time, method='previous'):
    """
    Retime hourly data to 5-minute intervals.
    
    Args:
        hourly_data: List of (timestamp, value) tuples with hourly data
        start_time: datetime - Start of optimization
        end_time: datetime - End of optimization
        method: 'previous' (step function) or 'linear' (interpolation)
    
    Returns:
        Tuple of (timesteps, values) at 5-minute intervals
    """
    timesteps = []
    current = start_time
    while current <= end_time:
        timesteps.append(current)
        current += timedelta(minutes=TIMESTEP_MINUTES)
    
    result = []
    hourly_dict = {ts: val for ts, val in hourly_data}
    
    for ts in timesteps:
        if method == 'previous':
            # Step function: use most recent hourly value
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            result.append(hourly_dict.get(hour_ts, 0))
        elif method == 'linear':
            # Linear interpolation between hourly points
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            next_hour_ts = hour_ts + timedelta(hours=1)
            
            val_before = hourly_dict.get(hour_ts, 0)
            val_after = hourly_dict.get(next_hour_ts, 0)
            
            minutes_elapsed = ts.minute
            fraction = minutes_elapsed / 60.0
            
            interpolated = val_before + (val_after - val_before) * fraction
            result.append(interpolated)
    
    return timesteps, result


def detect_shift_runs(activity_vector):
    """
    Detect contiguous runs of 1s in a binary activity vector.
    Each run represents a separate shift that can be optimized independently.
    
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
            # Create activity vector for this run
            run_activity = np.zeros(N)
            run_activity[start:end+1] = 1
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
                'max_forward_steps': int(forward_steps[phase_idx, start:end + 1].min()),
                'max_backward_steps': int(backward_steps[phase_idx, start:end + 1].min())
            })
    
    # Stack into matrix: nRuns x N
    if expanded_active:
        expanded_active = np.vstack(expanded_active)
    else:
        expanded_active = np.zeros((0, N))
    
    return expanded_active, expanded_info, expanded_names


def run_optimization(optimization_id):
    """
    Run the full optimization for an Optimization object, using the
    optimizer selected in its `optimizer` field.
    
    Returns:
        Updated Optimization object with results
    """
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
    
    # Validate data coverage
    generation_records = GenerationRecord.objects.filter(
        generation_dataset=generation_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    prices_records = PricesRecord.objects.filter(
        prices_dataset=prices_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    if not generation_records.exists() or not prices_records.exists():
        raise ValueError("The generation or prices data do not cover the reference week")
    
    # Build 5-minute timestep vector
    timesteps, _ = retime_hourly_to_5min([], start_time, end_time)
    N = len(timesteps)
    dt_h = TIMESTEP_MINUTES / 60.0  # Hours per step
    
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
    
    # Retime generation data to 5-minute intervals
    solar_hourly = [(r.timestamp, r.ele_generated_by_solar_kWh) for r in generation_records]
    cogen_hourly = [(r.timestamp, r.ele_generated_by_cogen_kWh) for r in generation_records]
    
    _, solar_5min = retime_hourly_to_5min(solar_hourly, start_time, end_time, method='linear')
    _, cogen_5min = retime_hourly_to_5min(cogen_hourly, start_time, end_time, method='linear')
    
    # Convert to kWh per step
    solar_5min_kWh = np.array([val * dt_h for val in solar_5min])
    cogen_5min_kWh = np.array([val * dt_h for val in cogen_5min])
    gen_kWh = solar_5min_kWh + cogen_5min_kWh
    
    # Retime prices data
    electricity_price_hourly = [(r.timestamp, r.electricity_price) for r in prices_records]
    _, electricity_price_5min = retime_hourly_to_5min(
        electricity_price_hourly, start_time, end_time, method='previous'
    )
    price_el = np.array(electricity_price_5min)
    
    # Run the selected optimizer
    problem = OptimizationProblem(
        elec_demand_matrix=elec_demand_matrix,
        gen_kWh=gen_kWh,
        price_el=price_el,
        max_shift_steps=np.array([min(info['max_forward_steps'], info['max_backward_steps'])
                                  for info in phase_info], dtype=int),
        run_info=phase_info
    )
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
            
            # Get original shift timing from phase_info
            original_start_step = info['original_start']
            original_end_step = info['original_end']
            
            # Apply shift
            new_start_step = original_start_step + current_shifts[i]
            new_end_step = original_end_step + current_shifts[i]
            
            # Convert back to day/hour/minute
            start_ts = timesteps[int(new_start_step)]
            # end_step is inclusive (last active timestep), so we need the END of that timestep
            # which is the START of the next timestep
            end_step_idx = int(new_end_step) + 1
            if end_step_idx < len(timesteps):
                end_ts = timesteps[end_step_idx]
            else:
                # If we're at the last timestep, add 5 minutes to it
                end_ts = timesteps[int(new_end_step)] + timedelta(minutes=TIMESTEP_MINUTES)
            
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
            'shift_changes': shift_changes,
            'num_timesteps': N,
            'num_runs_optimized': nPhases
        }
        
        optimization.save()
    
    return optimization
