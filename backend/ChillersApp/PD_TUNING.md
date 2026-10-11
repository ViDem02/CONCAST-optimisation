# ChillersApp Updates - PD Controller Tuning

## Changes Made

### 1. **Added PD Controller Parameters to Model**

New fields in `ChillerSimulation`:
- `proportional_gain` (Float, default=2.0) - Kp parameter for PD controller
- `derivative_gain` (Float, default=0.5) - Kd parameter for PD controller

These parameters control the PD controller behavior:
- **Kp (Proportional Gain)**: Controls response to current error
  - Higher values → faster response, but may cause overshooting
  - Lower values → slower, more stable response
  
- **Kd (Derivative Gain)**: Controls response to rate of change
  - Higher values → reduces oscillation and overshooting
  - Lower values → allows more oscillation

### 2. **Updated Admin Interface**

Added new fieldset in `ChillerSimulationAdmin`:
```python
('PD Controller Parameters', {
    'fields': ('proportional_gain', 'derivative_gain')
})
```

Now when creating/editing a simulation, you can set custom Kp and Kd values.

### 3. **Admin Action Already Available**

The admin action **"Run chiller simulation with PD control"** is already implemented and ready to use:

1. Go to Django Admin → ChillersApp → Chiller simulations
2. Select one or more simulations
3. Choose "Run chiller simulation with PD control" from the Actions dropdown
4. Click "Go"

Results will be displayed with success/error messages.

### 4. **Updated Simulation Logic**

The `run_chiller_simulation()` function now reads Kp and Kd from the simulation object:
```python
Kp = simulation.proportional_gain
Kd = simulation.derivative_gain
```

### 5. **Updated API Serializers**

Both `ChillerSimulationListSerializer` and `ChillerSimulationDetailSerializer` now include:
- `proportional_gain`
- `derivative_gain`

## Usage Examples

### Via Django Admin

1. **Create a Chiller**:
   - Name: "Cold Room 1"
   - U-value: 0.5 W/m²K
   - Surface area: 100 m²

2. **Create a ChillerSimulation**:
   - Name: "Test Run"
   - Chiller: "Cold Room 1"
   - Start date: 2024-01-01
   - End date: 2024-01-07
   - Min temp: 2°C
   - Max temp: 4°C
   - Heating rate: 0.1 °C/hour
   - Initial window: 2 hours
   - **Proportional gain: 2.0** (default)
   - **Derivative gain: 0.5** (default)

3. **Run Simulation**:
   - Check the simulation checkbox
   - Select "Run chiller simulation with PD control"
   - Click "Go"

4. **View Results**:
   - Open the simulation detail page
   - Expand "Results (Read-Only)" section
   - See temperature stats and power consumption

### Via API

```bash
# Create simulation with custom Kp and Kd
POST /api/chillers/chiller-simulations/
{
  "name": "Test with high Kp",
  "chiller": 1,
  "start_date": "2024-01-01",
  "end_date": "2024-01-07",
  "min_temperature": 2,
  "max_temperature": 4,
  "heating_rate": 0.1,
  "initial_window_hours": 2,
  "proportional_gain": 3.0,  // Faster response
  "derivative_gain": 0.8     // More damping
}

# Run the simulation
POST /api/chillers/chiller-simulations/1/run/
```

### Via Management Command

```bash
# Run with values set in database
python manage.py run_chiller_simulation 1

# Or by name
python manage.py run_chiller_simulation --simulation-name "Test Run"
```

## Tuning Guidelines

### Increasing Kp (Proportional Gain)
- ✅ Faster temperature response
- ✅ Reduces steady-state error
- ⚠️ May cause oscillation
- ⚠️ May cause overshooting

### Increasing Kd (Derivative Gain)
- ✅ Reduces oscillation
- ✅ Improves stability
- ✅ Prevents overshooting
- ⚠️ May amplify noise
- ⚠️ Slower to reach steady state

### Recommended Starting Values

**Standard cooling** (normal response):
- Kp = 2.0
- Kd = 0.5

**Aggressive cooling** (fast response):
- Kp = 3.0-4.0
- Kd = 0.8-1.0

**Conservative cooling** (stable, slow):
- Kp = 1.0-1.5
- Kd = 0.3-0.4

## Migration Applied

Migration `0002_chillersimulation_derivative_gain_and_more` has been applied:
- Added `proportional_gain` field with default=2.0
- Added `derivative_gain` field with default=0.5
- Existing simulations will use default values

## Testing

To test different PD parameters:

1. Create multiple simulations with same dates but different Kp/Kd
2. Run all simulations
3. Compare results:
   - Temperature stability
   - Oscillation behavior
   - Grid consumption
   - Waste levels

Use the results to find optimal parameters for your specific chiller setup.
