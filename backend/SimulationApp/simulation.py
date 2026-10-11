"""
Simulation calculation utilities for computing costs and electricity usage.

This module implements the core simulation logic that:
1. Retimes hourly datasets to 5-minute timesteps
2. Creates production/generation/prices matrices
3. Calculates electricity demand, generation, grid purchases, costs, and waste
"""

from datetime import datetime, timedelta
import pytz
from django.conf import settings
from PlanningApp.models import Simulation, Shift
from DatasetApp.models import GenerationRecord, PricesRecord
from .models import SimulationResults


def retime_hourly_to_5min(hourly_data, start_time, end_time, method='previous'):
    """
    Retime hourly data to 5-minute intervals.
    
    Args:
        hourly_data: List of (timestamp, value) tuples with hourly data
        start_time: datetime - Start of simulation
        end_time: datetime - End of simulation
        method: 'previous' (step function) or 'linear' (interpolation)
    
    Returns:
        List of values at 5-minute intervals
    """
    # Create 5-minute timestep vector
    timesteps = []
    current = start_time
    while current <= end_time:
        timesteps.append(current)
        current += timedelta(minutes=5)
    
    result = []
    hourly_dict = {ts: val for ts, val in hourly_data}
    
    for ts in timesteps:
        if method == 'previous':
            # Find the most recent hourly timestamp
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            result.append(hourly_dict.get(hour_ts, 0))
        elif method == 'linear':
            # Linear interpolation between hourly points
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            next_hour_ts = hour_ts + timedelta(hours=1)
            
            val_before = hourly_dict.get(hour_ts, 0)
            val_after = hourly_dict.get(next_hour_ts, 0)
            
            # Calculate fraction of hour elapsed
            minutes_elapsed = ts.minute
            fraction = minutes_elapsed / 60.0
            
            interpolated = val_before + (val_after - val_before) * fraction
            result.append(interpolated)
    
    return timesteps, result


def build_production_matrix(simulation, timesteps):
    """
    Build production matrix: N x M where N = timesteps, M = processes.
    Each cell is 1 if the process is running, 0 otherwise.
    
    Args:
        simulation: Simulation object
        timesteps: List of datetime objects at 5-minute intervals
    
    Returns:
        dict: {process_name: [values for each timestep]}
    """
    production_plan = simulation.reference_production_plan
    processes = production_plan.processes.all()
    
    production_matrix = {}
    
    for process in processes:
        # Initialize all timesteps to 0
        process_activity = [0] * len(timesteps)
        
        # Get all shifts for this process
        shifts = process.shifts.all()
        
        for shift in shifts:
            # For each timestep, check if it falls within this shift
            for i, ts in enumerate(timesteps):
                if is_timestep_in_shift(ts, shift):
                    process_activity[i] = 1
        
        production_matrix[process.name] = process_activity
    
    return production_matrix


def is_timestep_in_shift(timestamp, shift):
    """
    Check if a timestamp falls within a shift's time window.
    
    Handles multi-day shifts including week-spanning shifts.
    """
    weekday = timestamp.weekday()  # 0=Monday, 6=Sunday
    time_in_minutes = timestamp.hour * 60 + timestamp.minute
    
    start_minutes = shift.start_hour * 60 + shift.start_minutes
    end_minutes = shift.end_hour * 60 + shift.end_minutes
    
    # Same day shift
    if shift.start_day == shift.end_day:
        if weekday == shift.start_day:
            return start_minutes <= time_in_minutes < end_minutes
        return False
    
    # Multi-day shift
    # Check if start_day comes before end_day in the week
    if shift.start_day < shift.end_day:
        # Normal case: e.g., Monday to Thursday
        if weekday == shift.start_day:
            return time_in_minutes >= start_minutes
        elif weekday == shift.end_day:
            return time_in_minutes < end_minutes
        elif shift.start_day < weekday < shift.end_day:
            return True
    else:
        # Week-wrapping case: e.g., Friday to Monday (5 -> 1)
        if weekday == shift.start_day:
            return time_in_minutes >= start_minutes
        elif weekday == shift.end_day:
            return time_in_minutes < end_minutes
        elif weekday > shift.start_day or weekday < shift.end_day:
            return True
    
    return False


def calculate_electricity_demand(simulation, production_matrix, timesteps):
    """
    Calculate total electricity demand at each timestep.
    
    Args:
        production_matrix: dict of {process_name: [activity values]}
        timesteps: List of datetime objects
    
    Returns:
        List of electricity demand in kWh per 5-minute step
    """
    from PlanningApp.models import Process, WeeklyProductionPlan

    reference_plan:WeeklyProductionPlan = simulation.reference_production_plan 
    
    # Get electricity consumption for each process
    process_consumption = {}
    for process_name in production_matrix.keys():
        try:
            process = Process.objects.get(name=process_name, production_plan=reference_plan)
            # Convert kWh (hourly) to kWh per 5-minute step
            process_consumption[process_name] = process.electricity_consumption_kWh * (5 / 60)
        except Process.DoesNotExist:
            process_consumption[process_name] = 0
    
    # Calculate total demand at each timestep
    total_demand = []
    for i in range(len(timesteps)):
        demand = 0
        for process_name, activity in production_matrix.items():
            if activity[i] == 1:
                demand += process_consumption[process_name]
        total_demand.append(demand)
    
    return total_demand


def run_simulation_for_plan(simulation, production_plan, timesteps, start_time, end_time):
    """
    Run simulation for a specific production plan.
    
    Args:
        simulation: Simulation object
        production_plan: WeeklyProductionPlan to simulate
        timesteps: List of datetime objects at 5-minute intervals
        start_time: Start datetime
        end_time: End datetime
    
    Returns:
        dict with simulation results including costs and timestep data
    """
    generation_dataset = simulation.generation_dataset
    prices_dataset = simulation.prices_dataset
    
    # Temporarily set reference_production_plan for compatibility
    original_ref = simulation.reference_production_plan
    simulation.reference_production_plan = production_plan
    
    # 1. Build production matrix
    production_matrix = build_production_matrix(simulation, timesteps)
    
    # 2. Calculate electricity demand
    total_demand_kWh = calculate_electricity_demand(simulation, production_matrix, timesteps)
    
    # 3. Retime generation data to 5-minute intervals
    generation_records = GenerationRecord.objects.filter(
        generation_dataset=generation_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    solar_hourly = [(r.timestamp, r.ele_generated_by_solar_kWh) for r in generation_records]
    cogen_hourly = [(r.timestamp, r.ele_generated_by_cogen_kWh) for r in generation_records]
    
    _, solar_5min = retime_hourly_to_5min(solar_hourly, start_time, end_time, method='linear')
    _, cogen_5min = retime_hourly_to_5min(cogen_hourly, start_time, end_time, method='linear')
    
    # Convert hourly kWh to 5-minute kWh
    solar_5min_kWh = [val * (5 / 60) for val in solar_5min]
    cogen_5min_kWh = [val * (5 / 60) for val in cogen_5min]
    
    # 4. Retime prices data
    prices_records = PricesRecord.objects.filter(
        prices_dataset=prices_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    electricity_price_hourly = [(r.timestamp, r.electricity_price) for r in prices_records]
    _, electricity_price_5min = retime_hourly_to_5min(
        electricity_price_hourly, start_time, end_time, method='previous'
    )
    
    # 5. Calculate grid electricity and costs
    grid_electricity_kWh = []
    total_generation_kWh = []
    wasted_energy_kWh = []
    grid_cost_euros = []
    
    for i in range(len(timesteps)):
        gen_total = solar_5min_kWh[i] + cogen_5min_kWh[i]
        demand = total_demand_kWh[i]
        
        total_generation_kWh.append(gen_total)
        grid = max(0, demand - gen_total)
        grid_electricity_kWh.append(grid)
        waste = max(0, gen_total - demand)
        wasted_energy_kWh.append(waste)
        cost = grid * electricity_price_5min[i]
        grid_cost_euros.append(cost)
    
    # Restore original reference
    simulation.reference_production_plan = original_ref
    
    return {
        'total_demand_kWh': total_demand_kWh,
        'solar_generation_kWh': solar_5min_kWh,
        'cogen_generation_kWh': cogen_5min_kWh,
        'total_generation_kWh': total_generation_kWh,
        'grid_electricity_kWh': grid_electricity_kWh,
        'wasted_energy_kWh': wasted_energy_kWh,
        'electricity_price': electricity_price_5min,
        'grid_cost_euros': grid_cost_euros,
        'total_electricity_used': sum(total_demand_kWh),
        'total_grid_purchased': sum(grid_electricity_kWh),
        'total_solar_generated': sum(solar_5min_kWh),
        'total_cogen_generated': sum(cogen_5min_kWh),
        'total_wasted': sum(wasted_energy_kWh),
        'total_cost': sum(grid_cost_euros),
    }


def run_simulation(simulation_id):
    """
    Run the full simulation calculation for a given Simulation object.
    
    This function:
    1. Retimes hourly datasets to 5-minute timesteps
    2. Builds production, generation, and prices matrices for BOTH original and optimized plans
    3. Calculates electricity usage, grid purchases, costs, waste, CO2 for both plans
    4. Saves results to SimulationResults with separate costs
    
    Args:
        simulation_id: ID of the Simulation object to run
    
    Returns:
        SimulationResults object with calculated data
    """
    simulation = Simulation.objects.get(id=simulation_id)
    
    # Get datasets from simulation configuration
    generation_dataset = simulation.generation_dataset
    prices_dataset = simulation.prices_dataset
    
    if not generation_dataset:
        raise ValueError("Simulation must have a generation dataset configured")
    if not prices_dataset:
        raise ValueError("Simulation must have a prices dataset configured")
    
    # Get simulation time range
    tz = pytz.timezone(settings.TIME_ZONE)
    start_time = tz.localize(datetime.combine(simulation.start_date, datetime.min.time()))
    end_time = tz.localize(datetime.combine(simulation.end_date, datetime.max.time()))
    
    # Validate that datasets cover the simulation time range
    generation_records = GenerationRecord.objects.filter(
        generation_dataset=generation_dataset
    ).order_by('timestamp')
    
    prices_records = PricesRecord.objects.filter(
        prices_dataset=prices_dataset
    ).order_by('timestamp')
    
    if not generation_records.exists():
        raise ValueError(f"Generation dataset '{generation_dataset.name}' has no records")
    
    if not prices_records.exists():
        raise ValueError(f"Prices dataset '{prices_dataset.name}' has no records")
    
    gen_first = generation_records.first().timestamp
    gen_last = generation_records.last().timestamp
    prices_first = prices_records.first().timestamp
    prices_last = prices_records.last().timestamp
    
    # Check if datasets span covers simulation period
    required_start = start_time.replace(minute=0, second=0, microsecond=0)
    required_end = end_time.replace(minute=0, second=0, microsecond=0)
    
    if gen_first > required_start:
        raise ValueError(
            f"Generation dataset starts at {gen_first}, but simulation requires data from {required_start}. "
            f"Dataset is missing {(gen_first - required_start).total_seconds() / 3600:.1f} hours of data at the beginning."
        )
    
    if gen_last < required_end:
        raise ValueError(
            f"Generation dataset ends at {gen_last}, but simulation requires data until {required_end}. "
            f"Dataset is missing {(required_end - gen_last).total_seconds() / 3600:.1f} hours of data at the end."
        )
    
    if prices_first > required_start:
        raise ValueError(
            f"Prices dataset starts at {prices_first}, but simulation requires data from {required_start}. "
            f"Dataset is missing {(prices_first - required_start).total_seconds() / 3600:.1f} hours of data at the beginning."
        )
    
    if prices_last < required_end:
        raise ValueError(
            f"Prices dataset ends at {prices_last}, but simulation requires data until {required_end}. "
            f"Dataset is missing {(required_end - prices_last).total_seconds() / 3600:.1f} hours of data at the end."
        )
    
    # Build 5-minute timestep vector
    timesteps = []
    current = start_time
    while current <= end_time:
        timesteps.append(current)
        current += timedelta(minutes=5)
    
    num_timesteps = len(timesteps)
    
    # Determine which plans to run
    original_plan = simulation.original_production_plan or simulation.reference_production_plan
    optimized_plan = simulation.optimized_production_plan
    
    if not original_plan:
        raise ValueError("Simulation must have an original_production_plan or reference_production_plan")
    
    # Run simulation for original plan
    original_results = run_simulation_for_plan(simulation, original_plan, timesteps, start_time, end_time)
    
    # Run simulation for optimized plan (if available)
    if optimized_plan:
        optimized_results = run_simulation_for_plan(simulation, optimized_plan, timesteps, start_time, end_time)
        optimized_cost = optimized_results['total_cost']
        
        # Use optimized plan's data for aggregated metrics
        total_electricity_used = optimized_results['total_electricity_used']
        total_grid_purchased = optimized_results['total_grid_purchased']
        total_solar_generated = optimized_results['total_solar_generated']
        total_cogen_generated = optimized_results['total_cogen_generated']
        total_wasted = optimized_results['total_wasted']
        
        # Store both cost timeseries in timestep_data
        timestep_data = {
            'timestamps': [ts.isoformat() for ts in timesteps],
            'total_demand_kWh': optimized_results['total_demand_kWh'],
            'solar_generation_kWh': optimized_results['solar_generation_kWh'],
            'cogen_generation_kWh': optimized_results['cogen_generation_kWh'],
            'total_generation_kWh': optimized_results['total_generation_kWh'],
            'grid_electricity_kWh': optimized_results['grid_electricity_kWh'],
            'wasted_energy_kWh': optimized_results['wasted_energy_kWh'],
            'electricity_price': optimized_results['electricity_price'],
            'grid_cost_euros': optimized_results['grid_cost_euros'],
            'original_cost_euros': original_results['grid_cost_euros'],  # Original cost timeseries
            'optimized_cost_euros': optimized_results['grid_cost_euros'],  # Optimized cost timeseries
        }
    else:
        # Single plan simulation (backward compatibility)
        optimized_cost = 0
        total_electricity_used = original_results['total_electricity_used']
        total_grid_purchased = original_results['total_grid_purchased']
        total_solar_generated = original_results['total_solar_generated']
        total_cogen_generated = original_results['total_cogen_generated']
        total_wasted = original_results['total_wasted']
        
        timestep_data = {
            'timestamps': [ts.isoformat() for ts in timesteps],
            'total_demand_kWh': original_results['total_demand_kWh'],
            'solar_generation_kWh': original_results['solar_generation_kWh'],
            'cogen_generation_kWh': original_results['cogen_generation_kWh'],
            'total_generation_kWh': original_results['total_generation_kWh'],
            'grid_electricity_kWh': original_results['grid_electricity_kWh'],
            'wasted_energy_kWh': original_results['wasted_energy_kWh'],
            'electricity_price': original_results['electricity_price'],
            'grid_cost_euros': original_results['grid_cost_euros'],
        }
    
    original_cost = original_results['total_cost']
    
    # CO2 calculation (0.5 kg CO2 per kWh from grid)
    co2_factor = 0.5
    total_co2 = total_grid_purchased * co2_factor
    
    # Save results
    results, created = SimulationResults.objects.update_or_create(
        simulation=simulation,
        defaults={
            'total_electricity_used_kWh': total_electricity_used,
            'grid_electricity_purchased_kWh': total_grid_purchased,
            'solar_generated_kWh': total_solar_generated,
            'cogen_generated_kWh': total_cogen_generated,
            'wasted_energy_kWh': total_wasted,
            'original_cost_euros': original_cost,
            'optimized_cost_euros': optimized_cost,
            'total_cost_euros': optimized_cost if optimized_plan else original_cost,
            'total_co2_kg': total_co2,
            'timestep_minutes': 5,
            'num_timesteps': num_timesteps,
            'timestep_data': timestep_data,
        }
    )
    
    return results
