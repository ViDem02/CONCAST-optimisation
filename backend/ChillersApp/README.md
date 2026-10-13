# ChillersApp - Temperature Control with PD Controller

## Overview

The ChillersApp implements intelligent temperature control for chilled rooms using a **PD (Proportional-Derivative) controller**. The system minimizes grid electricity consumption and energy waste while maintaining temperature within specified constraints.

## Features

### 1. **PD Control Algorithm**
- **Proportional** term: Responds to current temperature error
- **Derivative** term: Responds to rate of change (prevents overshooting)
- Automatically adjusts cooling power to maintain target temperature

### 2. **Energy Optimization**
- **Prioritizes renewable energy**: Uses solar and cogeneration first
- **Opportunistic cooling**: Uses excess generation to pre-cool when available
- **Minimizes grid consumption**: Only draws from grid when necessary
- **Reduces waste**: Stores "cold" in thermal mass during surplus generation

### 3. **5-Minute Timesteps**
- High-resolution simulation for accurate control
- Converts hourly generation/price data to 5-minute intervals

### 4. **Initial Window**
- Configurable period where temperature can be outside normal range
- Useful for startup or non-critical periods
- After initial window, hard constraints are enforced

## Models

### Chiller
Represents a physical chilled room:
- `name`: Identifier
- `insulation_u_value`: Thermal insulation quality (W/m²·K)
- `surface_area`: Room surface area (m²)

### ChillerSimulation
Simulation configuration and results:
- `name`: Simulation identifier
- `chiller`: FK to Chiller
- `start_date`, `end_date`: Simulation period
- `min_temperature`, `max_temperature`: Acceptable temperature range (°C)
- `initial_window_hours`: Grace period for temperature constraints
- `proportional_gain`: Kp parameter for PD controller (default: 2.0)
- `derivative_gain`: Kd parameter for PD controller (default: 0.5)
- `chiller_power_delivery`: JSON results for power consumption
- `calculated_temperature`: JSON results for temperature evolution

**Note**: Heating rate is now calculated dynamically from the simulation's `TemperatureDataset` using the chiller's insulation properties.

## Usage

### 1. Django Admin

1. Create a Chiller in admin
2. Create a ChillerSimulation
3. Select the simulation and use **"Run chiller simulation with PD control"** action
4. View results in the detail page

### 2. Management Command

```bash
# Run by ID
python manage.py run_chiller_simulation 1

# Run by name
python manage.py run_chiller_simulation --simulation-name "Test Simulation"

# Run all simulations without results
python manage.py run_chiller_simulation --all
```

### 3. REST API

```bash
# List simulations
GET /api/chillers/chiller-simulations/

# Get simulation details (includes results)
GET /api/chillers/chiller-simulations/{id}/

# Run simulation
POST /api/chillers/chiller-simulations/{id}/run/

# Run simulation by ID in body
POST /api/chillers/chiller-simulations/run_by_id/
Body: {"simulation_id": 1}
```

## Algorithm Details

### Temperature Simulation
The heating rate is calculated dynamically based on heat transfer through insulation:

```
Q = U × A × ΔT (heat transfer in Watts)
heating_rate = Q × thermal_mass_coefficient
new_temp = current_temp + (heating_rate × dt) - (cooling_power × coefficient × dt)
```

Where:
- `U` = insulation_u_value (W/m²·K) from Chiller model
- `A` = surface_area (m²) from Chiller model
- `ΔT` = outside_temp - current_temp (from the simulation's TemperatureDataset)
- `thermal_mass_coefficient` = 0.0001 (calibration factor)

This provides realistic heating based on:
- External temperature conditions (from TemperatureDataset)
- Room insulation quality
- Temperature difference driving heat transfer

### PD Controller
```
control_output = Kp * error + Kd * (error - prev_error) / dt
```

Where:
- `error = target_temp - current_temp`
- `Kp = 2.0` (proportional gain)
- `Kd = 0.5` (derivative gain)
- `dt` = timestep in hours

### Energy Prioritization

1. **Calculate required cooling power** using PD controller
2. **Check available generation** (solar + cogeneration)
3. **If generation ≥ required**:
   - Use generation only
   - Excess becomes "wasted" (unless opportunistic cooling is applied)
4. **If generation < required**:
   - Use all generation
   - Draw remaining from grid
5. **Opportunistic cooling**:
   - If wasting >5 kW and temp > min_temp
   - Use excess for extra cooling (stores "cold" in thermal mass)

## Results Structure

### `chiller_power_delivery` JSON:
```json
{
  "timestamps": ["2024-01-01T00:00:00+01:00", ...],
  "power_kW": [12.5, 15.2, ...],
  "grid_consumption_kW": [0, 5.2, ...],
  "wasted_energy_kW": [3.5, 0, ...],
  "total_grid_consumption_kWh": 150.5,
  "total_wasted_kWh": 25.3,
  "total_cooling_kWh": 450.2
}
```

### `calculated_temperature` JSON:
```json
{
  "timestamps": ["2024-01-01T00:00:00+01:00", ...],
  "temperature_C": [2.5, 2.3, ...],
  "min_temp": 1.8,
  "max_temp": 3.2,
  "avg_temp": 2.5,
  "target_temp": 2.5,
  "min_allowed": 2.0,
  "max_allowed": 4.0
}
```

## Dependencies

Required for ChillersApp:
- `numpy` - Array operations and calculations
- `scipy` - Not directly used yet but available for optimization
- `matplotlib` - Plotting (optional, not installed in Docker; only needed by `generate_chiller_plots`)

**Datasets chosen in each simulation**:
- `GenerationDataset` - Solar and cogeneration data (not needed when a cost simulation is linked: its unused generation is used instead)
- `TemperatureDataset` - Outside temperature data (used for heating rate calculation)

## Configuration

### PD Controller Tuning

In `chiller_control.py`, adjust these parameters:
```python
Kp = 2.0  # Proportional gain (increase for faster response)
Kd = 0.5  # Derivative gain (increase to reduce oscillation)
```

### Thermal Model

Adjust cooling coefficient:
```python
cooling_coefficient = 0.5  # °C per kW per timestep
```

### Opportunistic Cooling

Adjust thresholds:
```python
if wasted_energy[i] > 5 and current_temp > simulation.min_temperature:
    extra_cooling = min(wasted_energy[i], 10)  # Max 10 kW extra
```

## Future Enhancements

1. **External temperature integration**: Use real weather data
2. **Advanced thermal model**: Include insulation_u_value and surface_area
3. **Predictive control**: Use forecast data for optimal pre-cooling
4. **Cost optimization**: Consider electricity prices in control decisions
5. **Multi-room optimization**: Coordinate multiple chillers
6. **Machine learning**: Learn optimal PD parameters from historical data

## Related Apps

- **DatasetApp**: Provides generation and price data
- **OptimizerApp**: Optimizes production schedules
- **PlanningApp**: Defines production plans
- **SimulationApp**: Runs production simulations

## Notes

- Choose the generation and temperature datasets in the simulation before running
- Simulation period must be covered by available data
- Initial window allows temperature violations during startup
- Results stored in JSON fields for flexibility
