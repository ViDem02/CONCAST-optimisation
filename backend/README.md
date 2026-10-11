# Simulator Project

Django + Django REST Framework project for production simulator based on the specifications in `Project.md`.

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

4. Create a superuser (optional):
```bash
python manage.py createsuperuser
```

5. Run the development server:
```bash
python manage.py runserver
```

## API Endpoints

The API is organized into three main sections:

### DatasetApp - `/api/datasets/`

Hourly timetable data for simulation inputs:
- **Temperature Datasets**: `/api/datasets/temperature-datasets/`
- **Prices Datasets**: `/api/datasets/prices-datasets/`
- **Generation Datasets**: `/api/datasets/generation-datasets/`

### PlanningApp - `/api/planning/`

Production planning and optimization:
- **Production Plans**: `/api/planning/production-plans/`
- **Processes**: `/api/planning/processes/`
- **Shifts**: `/api/planning/shifts/`
- **Simulations**: `/api/planning/simulations/`
- **Optimizations**: `/api/planning/optimizations/`

### ChillersApp - `/api/chillers/`

Chiller management and simulation:
- **Chillers**: `/api/chillers/chillers/`
- **Chiller Simulations**: `/api/chillers/chiller-simulations/`

Each endpoint supports standard REST operations:
- `GET` - List all items or retrieve a specific item
- `POST` - Create a new item
- `PUT/PATCH` - Update an existing item
- `DELETE` - Delete an item

## Data Models

### TemperatureDataset
Hourly timetable for temperature data.
- `is_active`: Boolean (only one can be true in the system)
- `name`: String (unique)
- `timestamp`: DateTime
- `outside_temperature`: Float

### PricesDataset
Hourly timetable for electricity and methane prices.
- `is_active`: Boolean (only one can be true in the system)
- `name`: String (unique)
- `timestamp`: DateTime
- `electricity_price`: Float (€/kWh)
- `methane_price`: Float (€/unit)

### GenerationDataset
Hourly timetable for electricity generation.
- `is_active`: Boolean (only one can be true in the system)
- `name`: String (unique)
- `timestamp`: DateTime
- `ele_generated_by_solar_kWh`: Float
- `ele_generated_by_cogen_kWh`: Float

### WeeklyProductionPlan
Weekly production plan with optimization flag.
- `name`: String (unique)
- `is_optimized`: Boolean (default: false)

### Process
Production process with electricity consumption.
- `name`: String (unique)
- `electricity_consumption_kWh`: Integer
- `production_plan`: Foreign key to WeeklyProductionPlan

### Shift
Shift schedule for a production process.
- `name`: String (unique)
- `process`: Foreign key to Process
- `start_day`: Integer (0-6, Monday-Sunday)
- `end_day`: Integer (0-6, Monday-Sunday)
- `start_hour`: Integer (0-23)
- `end_hour`: Integer (0-23)
- `max_forward_minutes`: Integer (must be multiple of 5)
- `max_backwards_minutes`: Integer (must be multiple of 5)

### Simulation
Simulation configuration.
- `name`: String (unique)
- `notes`: Text
- `reference_production_plan`: Foreign key to WeeklyProductionPlan
- `start_date`: Date
- `end_date`: Date

### Optimization
Optimization configuration and results.
- `name`: String (unique)
- `notes`: Text
- `reference_production_plan`: Foreign key to WeeklyProductionPlan
- `optimized_production_plan`: Foreign key to WeeklyProductionPlan (nullable)
- `reference_week`: Date

### Chiller
Chiller configuration for temperature control.
- `name`: String (unique)
- `insulation_u_value`: Float (W/m²K)
- `surface_area`: Float (m²)

### ChillerSimulation
Chiller simulation configuration and results.
- `name`: String (unique)
- `chiller`: Foreign key to Chiller
- `max_temperature`: Integer (°C)
- `min_temperature`: Integer (°C)
- `start_date`: Date
- `end_date`: Date
- `heating_rate`: Float (°C/hour)
- `initial_window_hours`: Integer
- `time_step`: Integer (choices: 1, 5, 10, 15, 30 minutes)
- `chiller_power_delivery`: JSON (results)
- `calculated_temperature`: JSON (results)

## Admin Interface

Access the Django admin interface at `http://localhost:8000/admin/` to manage all entities through a user-friendly interface.

## Next Steps

This project implements the data structures as specified. The following functionalities need to be implemented:

1. **Chillers planning** - Calculate when to turn on/off chillers using PD control
2. **Calculation of costs and usage** - Calculate electricity usage and costs based on simulation parameters
3. **Optimization of shifts** - Optimize shift timings to minimize costs (based on `simulator.m`)

These can be implemented as additional API endpoints or management commands.
