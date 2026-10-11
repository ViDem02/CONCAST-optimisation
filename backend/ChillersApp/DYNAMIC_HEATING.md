# ChillersApp Update - Dynamic Heating Rate from TemperatureDataset

## Summary

The `heating_rate` field has been removed from `ChillerSimulation` model. Instead, heating rate is now calculated **dynamically at each timestep** using:
1. Outside temperature from the active `TemperatureDataset`
2. Chiller insulation properties (`insulation_u_value` and `surface_area`)
3. Heat transfer physics (Q = U × A × ΔT)

## Changes Made

### 1. Model Changes (`ChillersApp/models.py`)
- ❌ Removed `heating_rate` field from `ChillerSimulation`
- ✅ Heating rate now derived from TemperatureDataset

### 2. Simulation Logic (`ChillersApp/chiller_control.py`)

**Added TemperatureDataset requirement:**
```python
temperature_dataset = TemperatureDataset.objects.get(is_active=True)
```

**Updated `simulate_temperature()` function:**
- Now accepts `chiller` object instead of static `heating_rate`
- Calculates heat transfer: `Q = U × A × ΔT`
- Where:
  - `U` = insulation_u_value (W/m²·K)
  - `A` = surface_area (m²)
  - `ΔT` = outside_temperature - room_temperature

**Dynamic temperature-based heating:**
- Retimes hourly temperature data to 5-minute intervals (linear interpolation)
- Uses actual outside temperature at each timestep
- Heating rate varies based on temperature difference

### 3. Admin Interface (`ChillersApp/admin.py`)
- Removed `heating_rate` from Temperature Control fieldset
- Form now only requires: min/max temperatures and initial_window_hours

### 4. API Serializers (`ChillersApp/serializers.py`)
- Removed `heating_rate` from both list and detail serializers
- API no longer accepts/returns heating_rate field

### 5. Migration
- Applied `0003_remove_chillersimulation_heating_rate`
- Existing simulations automatically updated

## How It Works

### Heat Transfer Calculation

At each 5-minute timestep:

1. **Get outside temperature** from TemperatureDataset
2. **Calculate temperature difference**: ΔT = T_outside - T_room
3. **Calculate heat transfer** (if outside is warmer):
   ```
   Q = U × A × ΔT  (Watts)
   ```
4. **Convert to temperature rise**:
   ```
   heating_rate = Q × thermal_mass_coefficient
   natural_heating = heating_rate × dt_hours
   ```
5. **Apply cooling** from chiller power delivery
6. **Update room temperature**:
   ```
   new_temp = current_temp + natural_heating - cooling
   ```

### Thermal Mass Coefficient

Currently set to `0.0001` (°C per Watt per hour). This is a calibration factor that depends on:
- Room volume
- Air density and specific heat
- Thermal mass of contents

**Can be adjusted in `chiller_control.py`:**
```python
thermal_mass_coefficient = 0.0001  # Tune based on actual room characteristics
```

## Benefits

### 1. **Realistic Physics**
- Heating rate varies with outside temperature
- Hot summer days → faster heating
- Cold winter days → slower heating
- Follows actual heat transfer principles

### 2. **Better Insulation Utilization**
- Chiller's `insulation_u_value` now affects simulation
- Better insulation → slower heating
- Larger surface area → more heat transfer

### 3. **Seasonal Accuracy**
- Summer simulations: higher outside temps → more cooling needed
- Winter simulations: lower outside temps → less cooling needed
- Reflects real-world seasonal variations

### 4. **Simplified Configuration**
- No need to estimate/configure heating_rate manually
- One less parameter to tune
- Automatic adaptation to temperature conditions

## Usage Example

### Creating a Simulation

**Before** (with static heating_rate):
```python
ChillerSimulation.objects.create(
    name="Test",
    chiller=my_chiller,
    min_temperature=2,
    max_temperature=4,
    heating_rate=0.1,  # ❌ Static value
    initial_window_hours=2
)
```

**After** (dynamic from TemperatureDataset):
```python
ChillerSimulation.objects.create(
    name="Test",
    chiller=my_chiller,
    min_temperature=2,
    max_temperature=4,
    initial_window_hours=2
    # ✅ heating_rate calculated from temperature data
)
```

### Prerequisites

Ensure you have an active TemperatureDataset with records covering your simulation period:

```python
# Create temperature dataset
temp_dataset = TemperatureDataset.objects.create(
    name="2024 Weather Data",
    is_active=True
)

# Add temperature records (hourly)
TemperatureRecord.objects.create(
    temperature_dataset=temp_dataset,
    timestamp=datetime(2024, 1, 1, 0, 0),
    outside_temperature=15.5  # °C
)
# ... more records
```

## Calibration

### Thermal Mass Coefficient

If simulation results don't match reality, adjust the thermal mass coefficient in `chiller_control.py`:

```python
# Current value
thermal_mass_coefficient = 0.0001

# For faster heating (lighter thermal mass):
thermal_mass_coefficient = 0.0002

# For slower heating (heavier thermal mass):
thermal_mass_coefficient = 0.00005
```

### Cooling Coefficient

Also adjustable:
```python
cooling_coefficient = 0.5  # °C per kW per timestep
```

Increase for more efficient cooling, decrease for less efficient cooling.

## Error Handling

The simulation will fail with clear error if:
- No active TemperatureDataset exists
- Temperature data doesn't cover simulation period
- Temperature records are missing

**Error message:**
```
ValueError: Active generation, prices, and temperature datasets must be available
```

**Solution:** Ensure active TemperatureDataset with complete data coverage.

## Testing

To verify the dynamic heating rate works correctly:

1. Create two simulations with identical parameters
2. Run one in summer period (high outside temps)
3. Run one in winter period (low outside temps)
4. Compare results:
   - Summer should require more cooling power
   - Winter should require less cooling power
   - Grid consumption should differ accordingly

## Future Enhancements

1. **Room volume parameter**: More accurate thermal mass calculation
2. **Humidity effects**: Latent heat considerations
3. **Solar radiation**: Direct heating from sunlight
4. **Infiltration**: Air exchange with outside
5. **Calibration tool**: Auto-tune thermal_mass_coefficient from historical data
