# Simulator Project

Django + Django REST Framework backend of SPARC: production-plan simulation, production-shift optimization and cold-room (chiller) control. The mathematical problem solved by the optimizers is defined in [docs/specification](../docs/specification/mathematical-specification.pdf); the rest of the documentation is indexed in [docs/README.md](../docs/README.md).

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

4. Create a superuser (needed to use the API and the frontend):
```bash
python manage.py createsuperuser
# or, non-interactively:
DJANGO_SUPERUSER_PASSWORD='<password>' python manage.py initadmin
```

5. Run the development server:
```bash
python manage.py runserver
```

## API Endpoints

Every endpoint requires an authenticated session (log in at `/admin/`). Unsafe requests (`POST`, `PUT`, `PATCH`, `DELETE`) also need the CSRF token in the `X-CSRFToken` header.

### DatasetApp - `/api/datasets/`

Hourly input data:
- **Temperature**: `/api/datasets/temperature-datasets/`, `/api/datasets/temperature-records/`
- **Prices**: `/api/datasets/prices-datasets/`, `/api/datasets/prices-records/`
- **Generation**: `/api/datasets/generation-datasets/`, `/api/datasets/generation-records/`

### PlanningApp - `/api/planning/`

Production plans and their simulations:
- **Production Plans**: `/api/planning/production-plans/`
- **Processes**: `/api/planning/processes/`
- **Shifts**: `/api/planning/shifts/`
- **Simulations**: `/api/planning/simulations/` (`POST …/{id}/run/` runs one)

### SimulationApp - `/api/simulation/`

- **Simulation Results**: `/api/simulation/simulation-results/` (also `…/{id}/timestep-data/`, `…/{id}/export-csv/` and `POST …/run-simulation/`)

### OptimizerApp - `/api/optimizer/`

- **Optimizations**: `/api/optimizer/optimizations/` (`POST …/{id}/run/` or `POST …/run_by_id/` runs one)

### ChillersApp - `/api/chillers/`

- **Chillers**: `/api/chillers/chillers/`
- **Chiller Simulations**: `/api/chillers/chiller-simulations/` (`POST …/{id}/run/`, `GET …/{id}/export_csv/`)

Each endpoint supports the standard REST operations:
- `GET` - List all items or retrieve a specific item
- `POST` - Create a new item
- `PUT/PATCH` - Update an existing item
- `DELETE` - Delete an item

## Data Models

### TemperatureDataset / PricesDataset / GenerationDataset
Named hourly datasets (`name`, unique; `is_active`). Their records hold a `timestamp` and:
- **TemperatureRecord**: `outside_temperature` (°C)
- **PricesRecord**: `electricity_price` (€/kWh), `methane_price`
- **GenerationRecord**: `ele_generated_by_solar_kWh`, `ele_generated_by_cogen_kWh`

### WeeklyProductionPlan
Weekly production plan (a template that repeats every week).
- `name`: String (unique)
- `is_optimized`: Boolean (default: false; true for plans created by an optimization)

### Process
Production process with electricity consumption.
- `name`: String (unique within a plan)
- `electricity_consumption_kWh`: Integer (energy drawn in one hour, i.e. power in kW)
- `production_plan`: Foreign key to WeeklyProductionPlan

### Shift
Shift schedule for a production process.
- `name`: String (unique within a process)
- `process`: Foreign key to Process
- `start_day`, `end_day`: Integer (0-6, Monday-Sunday)
- `start_hour`, `end_hour`: Integer (0-23)
- `start_minutes`, `end_minutes`: Integer (0-55, multiple of 5)
- `max_forward_minutes`, `max_backwards_minutes`: Integer (how far the shift may be moved; multiple of 5)

### Simulation
Evaluation of one or two plans over a period.
- `name`: String (unique)
- `notes`: Text
- `reference_production_plan`, `original_production_plan`, `optimized_production_plan`: Foreign keys to WeeklyProductionPlan
- `generation_dataset`, `prices_dataset`: Foreign keys to the datasets
- `start_date`, `end_date`: Date

### Optimization
Optimization configuration and results.
- `name`: String (unique)
- `notes`: Text
- `optimizer`: Optimization algorithm to use (default: `milp`, an exact MILP solved by HiGHS through `scipy.optimize.milp`; `from-scratch`, LSQR + coordinate descent, is the first method we experimented with and is kept for comparison). Available optimizers are registered in `OptimizerApp/optimizers/__init__.py`
- `reference_production_plan`: Foreign key to WeeklyProductionPlan
- `optimized_production_plan`: Foreign key to WeeklyProductionPlan (set when the optimization runs)
- `optimized_plan_name`: Name for the optimized plan (optional)
- `reference_week_start`, `reference_week_end`: Date
- `generation_dataset`, `prices_dataset`: Foreign keys to the datasets
- Results: `initial_cost_euros`, `optimized_cost_euros`, `cost_savings_euros`, `cost_savings_percent`, `optimization_data` (JSON diagnostics), `completed_at`

### Chiller
Cold-room configuration.
- `name`: String (unique)
- `insulation_u_value` (W/m²K), `surface_area` (m²)
- `nominal_capacity_kW`, `nominal_cooling_rate`, `chiller_efficiency`

### ChillerSimulation
PD-controlled cold-room simulation.
- `name`: String (unique)
- `chiller`: Foreign key to Chiller
- `min_temperature`, `max_temperature`, `target_temperature` (°C)
- `start_date`, `end_date`: Date
- `initial_window_hours`, `proportional_gain`, `derivative_gain`, `allow_grid_power`, `minimum_runtime_minutes`
- `production_plan_result`, `generation_dataset`, `prices_dataset`, `temperature_dataset`: inputs
- `chiller_power_delivery`, `calculated_temperature`: JSON results

See [ChillersApp/README.md](ChillersApp/README.md) for the control algorithm.

## Management Commands

| Command | Purpose |
| --- | --- |
| `import_generation_records`, `import_prices_records`, `import_temperature_records` | Load hourly CSV data ([guide](DatasetApp/IMPORT_COMMANDS.md)) |
| `import_production_plan`, `export_production_plan` | Load or export a weekly plan ([guide](PlanningApp/IMPORT_COMMANDS.md)) |
| `run_simulation`, `export_simulation_results` | Simulate plans and export the results |
| `run_optimization [--optimizer <name>]` | Optimize a plan's shifts |
| `run_chiller_simulation` | Run a chiller simulation |
| `initadmin` | Create the first admin account from `DJANGO_SUPERUSER_PASSWORD` |

## Admin Interface

Access the Django admin interface at `http://localhost:8000/admin/` to manage all entities through a user-friendly interface.
