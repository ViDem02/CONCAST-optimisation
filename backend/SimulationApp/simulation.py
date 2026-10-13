"""
Simulation calculation utilities for computing costs and electricity usage.

This module implements the core simulation logic that:
1. Retimes hourly datasets to 5-minute timesteps
2. Creates production/generation/prices matrices
3. Calculates electricity demand, generation, grid purchases, costs, and waste
"""

from datetime import datetime, timedelta
import numpy as np
import pytz
from django.conf import settings
from PlanningApp.models import Simulation
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


def minutes_of_week(timesteps):
    """Minute of the week (0 = Monday 00:00) of each timestep, as a numpy array."""
    return np.array([ts.weekday() * 1440 + ts.hour * 60 + ts.minute for ts in timesteps])


def shift_activity(week_minutes, shift):
    """
    Boolean array: True where the shift is running.

    Vectorized equivalent of is_timestep_in_shift (same handling of
    multi-day and week-wrapping shifts), with week_minutes from minutes_of_week.
    """
    start = shift.start_day * 1440 + shift.start_hour * 60 + shift.start_minutes
    end = shift.end_day * 1440 + shift.end_hour * 60 + shift.end_minutes
    if shift.start_day <= shift.end_day:
        return (week_minutes >= start) & (week_minutes < end)
    return (week_minutes >= start) | (week_minutes < end)  # Wraps around the end of the week


def build_production_matrix(production_plan, timesteps):
    """
    Activity of every process of the plan.

    Returns:
        dict: {process: boolean numpy array, True when the process runs at that timestep}
    """
    week_minutes = minutes_of_week(timesteps)
    matrix = {}
    for process in production_plan.processes.prefetch_related('shifts'):
        active = np.zeros(len(timesteps), dtype=bool)
        for shift in process.shifts.all():
            active |= shift_activity(week_minutes, shift)
        matrix[process] = active
    return matrix


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


def calculate_electricity_demand(production_matrix):
    """Total electricity demand (kWh per 5-minute step) at each timestep."""
    demand = 0
    for process, active in production_matrix.items():
        # Hourly consumption (kW) to kWh per 5-minute step
        demand = demand + active * process.electricity_consumption_kWh * (5 / 60)
    return np.asarray(demand, dtype=float)


def load_generation_and_prices(simulation, start_time, end_time):
    """Generation (kWh per step, solar and cogen) and price (EUR/kWh) on the 5-minute grid."""
    generation_records = GenerationRecord.objects.filter(
        generation_dataset=simulation.generation_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')

    solar_hourly = [(r.timestamp, r.ele_generated_by_solar_kWh) for r in generation_records]
    cogen_hourly = [(r.timestamp, r.ele_generated_by_cogen_kWh) for r in generation_records]

    _, solar_5min = retime_hourly_to_5min(solar_hourly, start_time, end_time, method='linear')
    _, cogen_5min = retime_hourly_to_5min(cogen_hourly, start_time, end_time, method='linear')

    prices_records = PricesRecord.objects.filter(
        prices_dataset=simulation.prices_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')

    electricity_price_hourly = [(r.timestamp, r.electricity_price) for r in prices_records]
    _, electricity_price_5min = retime_hourly_to_5min(
        electricity_price_hourly, start_time, end_time, method='previous'
    )

    # Convert hourly kWh to 5-minute kWh
    return (np.array(solar_5min) * (5 / 60), np.array(cogen_5min) * (5 / 60),
            np.array(electricity_price_5min, dtype=float))


def run_simulation_for_plan(production_plan, timesteps, solar_5min_kWh, cogen_5min_kWh, electricity_price_5min):
    """
    Run simulation for a specific production plan.

    Returns:
        dict with simulation results including costs and timestep data
    """
    total_demand_kWh = calculate_electricity_demand(build_production_matrix(production_plan, timesteps))
    total_generation_kWh = solar_5min_kWh + cogen_5min_kWh
    grid_electricity_kWh = np.maximum(0, total_demand_kWh - total_generation_kWh)
    wasted_energy_kWh = np.maximum(0, total_generation_kWh - total_demand_kWh)
    grid_cost_euros = grid_electricity_kWh * electricity_price_5min

    return {
        'total_demand_kWh': total_demand_kWh.tolist(),
        'solar_generation_kWh': solar_5min_kWh.tolist(),
        'cogen_generation_kWh': cogen_5min_kWh.tolist(),
        'total_generation_kWh': total_generation_kWh.tolist(),
        'grid_electricity_kWh': grid_electricity_kWh.tolist(),
        'wasted_energy_kWh': wasted_energy_kWh.tolist(),
        'electricity_price': electricity_price_5min.tolist(),
        'grid_cost_euros': grid_cost_euros.tolist(),
        'total_electricity_used': float(total_demand_kWh.sum()),
        'total_grid_purchased': float(grid_electricity_kWh.sum()),
        'total_solar_generated': float(solar_5min_kWh.sum()),
        'total_cogen_generated': float(cogen_5min_kWh.sum()),
        'total_wasted': float(wasted_energy_kWh.sum()),
        'total_cost': float(grid_cost_euros.sum()),
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
    
    for label, dataset, first, last in [('generation', generation_dataset, gen_first, gen_last),
                                        ('prices', prices_dataset, prices_first, prices_last)]:
        if first > required_start or last < required_end:
            raise ValueError(
                f"The {label} data \"{dataset.name}\" covers {first:%d %b %Y} to {last:%d %b %Y}, "
                f"but the simulation needs {required_start:%d %b %Y} to {required_end:%d %b %Y}. "
                f"Choose dates inside the data or upload more data."
            )
    
    # Build 5-minute timestep vector
    timesteps = []
    current = start_time
    while current <= end_time:
        timesteps.append(current)
        current += timedelta(minutes=5)
    
    num_timesteps = len(timesteps)
    
    # Determine which plans to run
    original_plan = simulation.original_production_plan
    optimized_plan = simulation.optimized_production_plan
    
    if not original_plan:
        raise ValueError("Simulation must have a current production plan")
    
    datasets = load_generation_and_prices(simulation, start_time, end_time)
    
    # Run simulation for original plan
    original_results = run_simulation_for_plan(original_plan, timesteps, *datasets)
    
    # Run simulation for the plan to compare (if available)
    if optimized_plan:
        optimized_results = run_simulation_for_plan(optimized_plan, timesteps, *datasets)
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
            'original_demand_kWh': original_results['total_demand_kWh'],
            'original_grid_electricity_kWh': original_results['grid_electricity_kWh'],
        }
    else:
        # Single plan simulation
        optimized_cost = None
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
            'total_co2_kg': total_co2,
            'timestep_minutes': 5,
            'num_timesteps': num_timesteps,
            'timestep_data': timestep_data,
        }
    )
    
    return results
