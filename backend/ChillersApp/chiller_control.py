"""
Chiller simulation module implementing PD control for temperature management.

This module implements the chiller planning functionality:
1. Uses PD (Proportional-Derivative) control to maintain temperature
2. Minimizes grid electricity consumption
3. Minimizes waste of produced energy
4. Works with 5-minute timesteps
"""

from datetime import datetime, timedelta
import pytz
import numpy as np
from django.conf import settings
from django.utils import timezone

from DatasetApp.models import GenerationRecord, TemperatureRecord
from .models import ChillerSimulation, Chiller


TIMESTEP_MINUTES = 5  # 5-minute timesteps


def retime_hourly_to_5min(hourly_data, start_time, end_time, method='previous'):
    """
    Retime hourly data to 5-minute intervals.
    
    Args:
        hourly_data: List of (timestamp, value) tuples with hourly data
        start_time: datetime - Start time
        end_time: datetime - End time
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
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            result.append(hourly_dict.get(hour_ts, 0))
        elif method == 'linear':
            hour_ts = ts.replace(minute=0, second=0, microsecond=0)
            next_hour_ts = hour_ts + timedelta(hours=1)
            
            val_before = hourly_dict.get(hour_ts, 0)
            val_after = hourly_dict.get(next_hour_ts, 0)
            
            minutes_elapsed = ts.minute
            fraction = minutes_elapsed / 60.0
            
            interpolated = val_before + (val_after - val_before) * fraction
            result.append(interpolated)
    
    return timesteps, result


def pd_controller(error, prev_error, Kp, Kd, dt):
    """
    PD (Proportional-Derivative) controller.
    
    Args:
        error: Current error (target - current)
        prev_error: Previous error
        Kp: Proportional gain
        Kd: Derivative gain
        dt: Time step in hours
    
    Returns:
        Control output (power in kW)
    """
    proportional = Kp * error
    derivative = Kd * (error - prev_error) / dt if dt > 0 else 0
    
    return proportional + derivative


def simulate_temperature(
    initial_temp,
    external_temp,
    power_delivery,
    chiller,
    dt_hours
):
    """
    Simulate temperature change based on external temperature and cooling power.
    
    Args:
        initial_temp: Initial temperature (°C)
        external_temp: External temperature (°C)
        power_delivery: Cooling power delivered (kW)
        chiller: Chiller object with insulation properties
        dt_hours: Time step in hours
    
    Returns:
        New temperature (°C)
    """
    # Calculate natural heating rate based on temperature difference and insulation
    # Q = U * A * ΔT (heat transfer through insulation)
    # U = insulation_u_value (W/m²K)
    # A = surface_area (m²)
    # ΔT = temperature difference (K or °C)
    temp_difference = external_temp - initial_temp
    
    if temp_difference > 0:
        # Heat transfer in Watts: Q = U * A * ΔT
        heat_transfer_watts = chiller.insulation_u_value * chiller.surface_area * temp_difference
        
        # Convert to temperature rise (simplified: assuming room thermal mass)
        # Calibrated: 1000 Watts (1 kW) → approximately 0.3°C/hour rise for typical cold room
        # This coefficient should be calibrated based on room volume and thermal mass
        thermal_mass_coefficient = 0.0003  # °C per Watt per hour
        heating_rate = heat_transfer_watts * thermal_mass_coefficient
        natural_heating = heating_rate * dt_hours
    else:
        natural_heating = 0
    
    # Cooling from chiller
    # Use the chiller's nominal capacity to determine cooling effectiveness
    # cooling_rate = (power_delivery / nominal_capacity) * efficiency * nominal_cooling_rate
    # At nominal capacity with 100% efficiency, the chiller removes heat at its designed rate
    
    # Apply chiller efficiency to reduce cooling power if chiller is less powerful
    effective_cooling = power_delivery * chiller.chiller_efficiency
    
    # Calculate actual cooling based on proportion of nominal capacity being used
    if chiller.nominal_capacity_kW > 0:
        cooling_rate = (effective_cooling / chiller.nominal_capacity_kW) * chiller.nominal_cooling_rate
        cooling = cooling_rate * dt_hours
    else:
        cooling = 0
    
    # New temperature
    new_temp = initial_temp + natural_heating - cooling
    
    return new_temp


def run_chiller_simulation(simulation_id):
    """
    Run chiller simulation with PD control.
    
    Maintains temperature within specified range while:
    - Minimizing grid electricity consumption
    - Minimizing waste of produced energy
    
    Args:
        simulation_id: ID of ChillerSimulation object
    
    Returns:
        Updated ChillerSimulation object with results
    """
    simulation = ChillerSimulation.objects.get(id=simulation_id)
    chiller = simulation.chiller
    
    # Get PD controller parameters from simulation
    Kp = simulation.proportional_gain
    Kd = simulation.derivative_gain
    
    # Get datasets from simulation object
    generation_dataset = simulation.generation_dataset
    temperature_dataset = simulation.temperature_dataset
    
    if not temperature_dataset:
        raise ValueError("Choose the outside temperature data of the simulation")
    if not generation_dataset and not simulation.production_plan_result:
        raise ValueError("Choose the on-site generation data of the simulation (or link a cost simulation)")
    
    # Get simulation time range
    tz = pytz.timezone(settings.TIME_ZONE)
    start_time = tz.localize(datetime.combine(simulation.start_date, datetime.min.time()))
    end_time = tz.localize(datetime.combine(simulation.end_date, datetime.max.time()))
    
    # Validate data coverage
    generation_records = GenerationRecord.objects.filter(
        generation_dataset=generation_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    temperature_records = TemperatureRecord.objects.filter(
        temperature_dataset=temperature_dataset,
        timestamp__gte=start_time.replace(minute=0, second=0),
        timestamp__lte=end_time
    ).order_by('timestamp')
    
    if not temperature_records.exists() or (not simulation.production_plan_result and not generation_records.exists()):
        raise ValueError("The generation or temperature data do not cover the simulation period")
    
    # Build 5-minute timestep vector
    timesteps, _ = retime_hourly_to_5min([], start_time, end_time)
    N = len(timesteps)
    dt_h = TIMESTEP_MINUTES / 60.0  # Hours per step
    
    # Check if linked to production plan - use wasted energy instead of full generation
    if simulation.production_plan_result:
        # Use wasted energy from production plan as available generation
        production_timestep_data = simulation.production_plan_result.timestep_data
        
        if not production_timestep_data or 'wasted_energy_kWh' not in production_timestep_data:
            raise ValueError("The linked cost simulation has no results: run it first")
        
        # Get wasted energy from production plan (in kWh per timestep)
        wasted_kWh_list = production_timestep_data['wasted_energy_kWh']
        
        # Validate timestep count matches
        if len(wasted_kWh_list) != N:
            raise ValueError("The linked cost simulation must cover exactly the same dates as this simulation")
        
        # Convert from kWh to kW (production plan uses same 5-minute timesteps)
        # kWh per 5-minute timestep → kW: multiply by (60/5) = 12
        total_generation_kW = np.array(wasted_kWh_list) * 12
    else:
        # Use full generation from datasets (original behavior)
        # Retime generation data to 5-minute intervals
        solar_hourly = [(r.timestamp, r.ele_generated_by_solar_kWh) for r in generation_records]
        cogen_hourly = [(r.timestamp, r.ele_generated_by_cogen_kWh) for r in generation_records]
        
        _, solar_5min = retime_hourly_to_5min(solar_hourly, start_time, end_time, method='linear')
        _, cogen_5min = retime_hourly_to_5min(cogen_hourly, start_time, end_time, method='linear')
        
        # Convert to kW (from hourly kWh to instantaneous power)
        solar_kW = np.array(solar_5min)
        cogen_kW = np.array(cogen_5min)
        total_generation_kW = solar_kW + cogen_kW
    
    # Retime temperature data (linear interpolation for smooth temperature changes)
    temperature_hourly = [(r.timestamp, r.outside_temperature) for r in temperature_records]
    _, temperature_5min = retime_hourly_to_5min(
        temperature_hourly, start_time, end_time, method='linear'
    )
    outside_temps = np.array(temperature_5min)
    
    # Initialize arrays for results
    temperatures = np.zeros(N)
    power_delivery = np.zeros(N)
    grid_consumption = np.zeros(N)
    wasted_energy = np.zeros(N)
    
    # Target temperature (use manual setting if provided, otherwise midpoint of range)
    if simulation.target_temperature is not None:
        target_temp = simulation.target_temperature
    else:
        target_temp = (simulation.min_temperature + simulation.max_temperature) / 2.0
    
    # Set initial temperature (start at target)
    initial_temp = target_temp
    temperatures[0] = initial_temp
    
    # Initial window steps (period where temperature can be outside range)
    initial_window_steps = int(simulation.initial_window_hours * 60 / TIMESTEP_MINUTES)
    
    # Previous error for derivative term
    prev_error = 0
    
    # Minimum runtime tracking
    chiller_running = False
    runtime_remaining_steps = 0
    min_runtime_steps = int(simulation.minimum_runtime_minutes / TIMESTEP_MINUTES)
    
    # Simulation loop
    for i in range(N):
        current_temp = temperatures[i]
        
        # Calculate error (current - target)
        # If temp is too high (current > target), error is positive → increase cooling
        # If temp is too low (current < target), error is negative → decrease cooling
        error = current_temp - target_temp
        
        # After initial window, enforce hard constraints
        if i >= initial_window_steps:
            if current_temp > simulation.max_temperature:
                # Temperature too high - aggressive cooling needed
                error = current_temp - target_temp + (current_temp - simulation.max_temperature)
            elif current_temp < simulation.min_temperature:
                # Temperature too low - stop cooling
                error = -abs(current_temp - target_temp)
        
        # PD control to determine required cooling power
        required_power = pd_controller(error, prev_error, Kp, Kd, dt_h)
        
        # Ensure power is non-negative (can't heat with a chiller)
        required_power = max(0, required_power)
        
        # Apply minimum runtime constraint
        if min_runtime_steps > 0:
            if runtime_remaining_steps > 0:
                # Chiller must keep running
                runtime_remaining_steps -= 1
                chiller_running = True
                # Ensure minimum power delivery to keep chiller running
                required_power = max(required_power, 1.0)  # At least 1 kW
            elif required_power > 0.5:  # Threshold to start chiller (prevents noise)
                # Start chiller - commit to minimum runtime
                chiller_running = True
                runtime_remaining_steps = min_runtime_steps - 1
            else:
                # Don't start chiller for tiny power requirements
                required_power = 0
                chiller_running = False
        
        # Prioritize using available generation
        available_gen = total_generation_kW[i]
        
        if required_power <= available_gen:
            # Use generation only
            power_delivery[i] = required_power
            grid_consumption[i] = 0
            wasted_energy[i] = available_gen - required_power
        else:
            # Need more power than available generation
            if simulation.allow_grid_power:
                # Use grid power
                power_delivery[i] = required_power
                grid_consumption[i] = required_power - available_gen
                wasted_energy[i] = 0
            else:
                # Grid power not allowed - use only available generation
                power_delivery[i] = available_gen
                grid_consumption[i] = 0
                wasted_energy[i] = 0
        
        # Opportunistic cooling: use excess generation when available
        # Only if minimum runtime constraint allows it (chiller is running or can start)
        if wasted_energy[i] > 5 and current_temp > simulation.min_temperature:
            can_use_extra = True
            
            # Check if minimum runtime constraint would prevent starting
            if min_runtime_steps > 0 and not chiller_running:
                # Would need to start chiller - don't do opportunistic cooling
                # unless it's worth committing to the minimum runtime
                can_use_extra = False
            
            if can_use_extra:
                # Use excess generation for extra cooling
                extra_cooling = min(wasted_energy[i], 10)  # Limited extra cooling
                
                # If this starts the chiller, commit to minimum runtime
                if min_runtime_steps > 0 and power_delivery[i] == 0 and extra_cooling > 0:
                    chiller_running = True
                    runtime_remaining_steps = min_runtime_steps - 1
                    extra_cooling = max(extra_cooling, 1.0)  # Ensure minimum power
                
                power_delivery[i] += extra_cooling
                wasted_energy[i] -= extra_cooling
        
        # Update error for next iteration
        prev_error = error
        
        # Calculate next temperature (if not last step)
        if i < N - 1:
            # Get external temperature from dataset
            external_temp = outside_temps[i]
            
            temperatures[i + 1] = simulate_temperature(
                current_temp,
                external_temp,
                power_delivery[i],
                chiller,
                dt_h
            )
    
    # Save results to simulation object
    simulation.chiller_power_delivery = {
        'timestamps': [ts.isoformat() for ts in timesteps],
        'power_kW': power_delivery.tolist(),
        'grid_consumption_kW': grid_consumption.tolist(),
        'wasted_energy_kW': wasted_energy.tolist(),
        'total_grid_consumption_kWh': float(np.sum(grid_consumption) * dt_h),
        'total_wasted_kWh': float(np.sum(wasted_energy) * dt_h),
        'total_cooling_kWh': float(np.sum(power_delivery) * dt_h)
    }
    
    simulation.calculated_temperature = {
        'timestamps': [ts.isoformat() for ts in timesteps],
        'temperature_C': temperatures.tolist(),
        'outside_temperature_C': outside_temps.tolist(),
        'min_temp': float(np.min(temperatures)),
        'max_temp': float(np.max(temperatures)),
        'avg_temp': float(np.mean(temperatures)),
        'target_temp': float(target_temp),
        'min_allowed': simulation.min_temperature,
        'max_allowed': simulation.max_temperature
    }
    
    simulation.save()
    
    return simulation


def generate_chiller_plots(simulation_id, output_dir=None):
    """
    Generate plots for chiller simulation results.
    
    Args:
        simulation_id: ID of ChillerSimulation object
        output_dir: Directory to save plots (optional)
    
    Returns:
        Dictionary with plot file paths or figure objects
    """
    import matplotlib.pyplot as plt
    
    simulation = ChillerSimulation.objects.get(id=simulation_id)
    
    if not simulation.chiller_power_delivery or not simulation.calculated_temperature:
        raise ValueError("Simulation has not been run yet")
    
    # Extract data
    timestamps = [datetime.fromisoformat(ts) for ts in simulation.calculated_temperature['timestamps']]
    temperatures = simulation.calculated_temperature['temperature_C']
    power_delivery = simulation.chiller_power_delivery['power_kW']
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # Plot 1: Temperature over time
    ax1.plot(timestamps, temperatures, 'b-', linewidth=2, label='Actual Temperature')
    ax1.axhline(y=simulation.max_temperature, color='r', linestyle='--', 
                label=f'Max Allowed ({simulation.max_temperature}°C)')
    ax1.axhline(y=simulation.min_temperature, color='r', linestyle='--', 
                label=f'Min Allowed ({simulation.min_temperature}°C)')
    ax1.axhline(y=simulation.calculated_temperature['target_temp'], 
                color='g', linestyle=':', label='Target')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Temperature (°C)')
    ax1.set_title('Chilled Room Temperature Over Time')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Power delivery
    ax2.plot(timestamps, power_delivery, 'r-', linewidth=2, label='Cooling Power')
    ax2.set_xlabel('Time')
    ax2.set_ylabel('Power (kW)')
    ax2.set_title('Chiller Power Delivery')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_dir:
        import os
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'chiller_simulation_{simulation.id}.png')
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        return {'plot_path': output_path}
    else:
        return {'figure': fig}
