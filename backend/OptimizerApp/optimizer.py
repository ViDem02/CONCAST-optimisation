"""
Shift optimization module implementing LSQR initialization and coordinate descent.

This module implements the optimization logic from simulator.m:
1. Retimes hourly datasets to 5-minute timesteps
2. Builds production timetable matrix (nPhases x N) where each row is a phase activity
3. Expands phases to independent runs (contiguous activity periods)
4. Uses LSQR for initial shift estimation
5. Refines with coordinate descent to minimize costs
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
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import lsqr
from django.conf import settings
from django.utils import timezone
from django.db import transaction


TIMESTEP_MINUTES = 5  # 5-minute timesteps
MAX_ITERATIONS = 500  # Maximum iterations for coordinate descent


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
    Build production matrix (like simulator.m): N x nPhases where N = timesteps.
    Each column represents a process with its complete activity pattern.
    
    This follows the MATLAB approach where each process gets one column initially,
    and we'll expand to multiple runs per process later.
    
    Returns:
        Tuple of (phase_active, phase_info) where:
        - phase_active: numpy array of shape (nPhases, N) with binary activity
        - phase_info: list of dicts with process info for each phase
    """
    from SimulationApp.simulation import is_timestep_in_shift
    
    processes = production_plan.processes.all()
    nPhases = len(processes)
    N = len(timesteps)
    
    # Build activity matrix: nPhases x N
    phase_active = np.zeros((nPhases, N))
    phase_info = []
    
    for phase_idx, process in enumerate(processes):
        # Get all shifts for this process
        shifts = process.shifts.all()
        
        # Mark timesteps where process is active
        for shift in shifts:
            for i, ts in enumerate(timesteps):
                if is_timestep_in_shift(ts, shift):
                    phase_active[phase_idx, i] = 1
        
        # Get shift limits (assume all shifts in process have same limits)
        shift = shifts.first()
        max_forward_steps = shift.max_forward_minutes // TIMESTEP_MINUTES if shift else 24
        max_backward_steps = shift.max_backwards_minutes // TIMESTEP_MINUTES if shift else 24
        
        phase_info.append({
            'process_id': process.id,
            'process_name': process.name,
            'electricity_consumption_kWh': process.electricity_consumption_kWh,
            'max_forward_steps': max_forward_steps,
            'max_backward_steps': max_backward_steps
        })
    
    return phase_active, phase_info


def expand_phases_to_runs(phase_active, phase_info):
    """
    Expand phases to multiple runs (like simulator.m does).
    Each contiguous run of activity becomes an independent optimizable unit.
    
    Args:
        phase_active: nPhases x N binary matrix
        phase_info: list of phase information dicts
    
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
                'max_forward_steps': info['max_forward_steps'],
                'max_backward_steps': info['max_backward_steps']
            })
    
    # Stack into matrix: nRuns x N
    if expanded_active:
        expanded_active = np.vstack(expanded_active)
    else:
        expanded_active = np.zeros((0, N))
    
    return expanded_active, expanded_info, expanded_names


def apply_shifts_from_steps(base_matrix, shift_steps):
    """
    Apply time shifts to each row of the phase activity matrix.
    This follows simulator.m's apply_shifts_from_steps function.
    
    Args:
        base_matrix: nPhases x N numpy array
        shift_steps: array of nPhases integers (positive = delay, negative = advance)
    
    Returns:
        Shifted nPhases x N numpy array
    """
    nPhases, N = base_matrix.shape
    shifted = np.zeros_like(base_matrix)
    
    for i in range(nPhases):
        shift = int(shift_steps[i])
        original = base_matrix[i, :]
        
        if shift == 0:
            shifted[i, :] = original
        elif shift > 0:
            # Delay: shift forward
            shifted[i, shift:] = original[:-shift]
        else:
            # Advance: shift backward
            shifted[i, :shift] = original[-shift:]
    
    return shifted


def compute_cost(elec_demand, gen_kWh, price_el):
    """
    Compute total cost based on demand, generation, and prices.
    
    Cost = sum(grid_purchase * price_el)
    where grid_purchase = max(0, demand - generation)
    
    Also tracks wasted energy = max(0, generation - demand)
    """
    grid_purchase = np.maximum(0, elec_demand - gen_kWh)
    wasted_energy = np.maximum(0, gen_kWh - elec_demand)
    
    cost_el = np.sum(grid_purchase * price_el)
    total_wasted = np.sum(wasted_energy)
    
    return cost_el, {
        'grid_purchase': grid_purchase,
        'wasted_energy': wasted_energy,
        'total_wasted': total_wasted
    }


def run_optimization(optimization_id):
    """
    Run the full optimization for an Optimization object.
    
    Implements LSQR initialization + coordinate descent refinement
    following the algorithm in simulator.m
    
    Returns:
        Updated Optimization object with results
    """
    # Import models here to avoid circular imports
    from PlanningApp.models import WeeklyProductionPlan, Process, Shift
    from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
    from .models import Optimization
    
    optimization = Optimization.objects.get(id=optimization_id)
    
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
        raise ValueError("Insufficient data coverage for reference week")
    
    # Build 5-minute timestep vector
    timesteps, _ = retime_hourly_to_5min([], start_time, end_time)
    N = len(timesteps)
    dt_h = TIMESTEP_MINUTES / 60.0  # Hours per step
    
    # Build production matrix: nPhases x N (following simulator.m approach)
    phase_active, phase_info = build_production_matrix(
        optimization.reference_production_plan,
        timesteps
    )
    
    # Expand to multiple runs per phase (like simulator.m does)
    phase_active, phase_info, phase_names = expand_phases_to_runs(phase_active, phase_info)
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
    
    # LSQR Initialization (following simulator.m)
    # Build sparse matrix A for LSQR where each column represents a shift option
    max_shift_steps = max([max(info['max_forward_steps'], info['max_backward_steps']) 
                           for info in phase_info] + [24])  # At least ±2 hours
    
    shift_candidates = list(range(-max_shift_steps, max_shift_steps + 1))
    n_shifts = len(shift_candidates)
    
    A = lil_matrix((N, nPhases * n_shifts))
    col_idx = 0
    
    for i in range(nPhases):
        for shift_step in shift_candidates:
            # Check if shift is within allowed bounds for this phase
            info = phase_info[i]
            if abs(shift_step) <= min(info['max_forward_steps'], info['max_backward_steps']):
                shifted_col = np.zeros(N)
                original = elec_demand_matrix[i, :]  # Row i of demand matrix
                
                if shift_step == 0:
                    shifted_col = original
                elif shift_step > 0:
                    shifted_col[shift_step:] = original[:-shift_step]
                else:
                    shifted_col[:shift_step] = original[-shift_step:]
                
                A[:, col_idx] = shifted_col.reshape(-1, 1)
            
            col_idx += 1
    
    A = A.tocsr()
    b = gen_kWh
    
    # Run LSQR
    x_lsqr, istop, itn, r1norm = lsqr(A, b, atol=1e-6, btol=1e-6, iter_lim=500)[:4]
    
    # Extract initial shifts from LSQR solution, respecting per-run bounds
    initial_shifts = np.zeros(nPhases, dtype=int)
    col_ptr = 0
    for i in range(nPhases):
        run_cols = x_lsqr[col_ptr:col_ptr + n_shifts]
        col_ptr += n_shifts

        # Allowed range in steps for this run
        max_steps_allowed = min(phase_info[i]['max_forward_steps'], phase_info[i]['max_backward_steps'])

        # Build list of indices that are within allowed bounds
        allowed_indices = [idx for idx, s in enumerate(shift_candidates) if abs(s) <= max_steps_allowed]

        if allowed_indices:
            # Pick the best among allowed indices
            best_idx_local = allowed_indices[0]
            best_val = run_cols[best_idx_local]
            for idx in allowed_indices:
                if run_cols[idx] > best_val:
                    best_idx_local = idx
                    best_val = run_cols[idx]
            chosen_shift = shift_candidates[best_idx_local]
        else:
            # No allowed shifts? default to 0
            chosen_shift = 0

        # Extra safety: clamp to allowed range
        chosen_shift = int(max(-max_steps_allowed, min(max_steps_allowed, chosen_shift)))
        initial_shifts[i] = chosen_shift
    
    # Calculate initial cost with LSQR shifts
    shifted_demand = apply_shifts_from_steps(elec_demand_matrix, initial_shifts)
    total_demand = shifted_demand.sum(axis=0)  # Sum across phases (axis=0) to get total per timestep
    initial_cost, _ = compute_cost(total_demand, gen_kWh, price_el)
    
    # Baseline cost (no optimization)
    baseline_demand = elec_demand_matrix.sum(axis=0)  # Sum across phases
    baseline_cost, _ = compute_cost(baseline_demand, gen_kWh, price_el)
    
    # Coordinate Descent Refinement (following simulator.m)
    # Ensure current shifts start within bounds
    current_shifts = initial_shifts.copy()
    for i in range(nPhases):
        max_steps_allowed = min(phase_info[i]['max_forward_steps'], phase_info[i]['max_backward_steps'])
        current_shifts[i] = int(max(-max_steps_allowed, min(max_steps_allowed, current_shifts[i])))
    best_cost = initial_cost
    improved = True
    iteration = 0
    max_iterations = 5 * nPhases
    
    while improved and iteration < max_iterations:
        improved = False
        
        for i in range(nPhases):
            info = phase_info[i]
            current_shift = current_shifts[i]
            
            # Try shifting this phase by ±1 step
            for delta in [-1, +1]:
                new_shift = current_shift + delta
                
                # Check bounds
                if abs(new_shift) > min(info['max_forward_steps'], info['max_backward_steps']):
                    continue
                
                # Test this shift
                test_shifts = current_shifts.copy()
                test_shifts[i] = new_shift
                
                shifted_demand = apply_shifts_from_steps(elec_demand_matrix, test_shifts)
                total_demand = shifted_demand.sum(axis=0)  # Sum across phases
                test_cost, _ = compute_cost(total_demand, gen_kWh, price_el)
                
                if test_cost < best_cost:
                    best_cost = test_cost
                    current_shifts[i] = new_shift
                    improved = True
                    break  # Move to next phase
        
        iteration += 1
    
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
            'lsqr_iterations': int(itn),
            'lsqr_residual': float(r1norm),
            'coordinate_descent_iterations': iteration,
            'initial_cost_after_lsqr': float(initial_cost),
            'baseline_cost': float(baseline_cost),
            'final_cost': float(final_cost),
            'total_wasted_energy': float(final_details['total_wasted']),
            'shift_changes': shift_changes,
            'num_timesteps': N,
            'num_runs_optimized': nPhases
        }
        
        optimization.save()
    
    return optimization
