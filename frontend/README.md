# CONCAST Simulator - Frontend

React frontend for viewing simulation results.

## Setup

```bash
cd simulator_project/frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`

## Prerequisites

- Node.js 18+
- Django backend at `http://localhost:8000`
- CORS configured in Django:
  ```python
  INSTALLED_APPS = [..., 'corsheaders', ...]
  MIDDLEWARE = [..., 'corsheaders.middleware.CorsMiddleware', ...]
  CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
  ```

## Usage

**Run simulations via Django:**
```bash
python manage.py run_simulation <simulation_id>
```

**View results:**
Open frontend → Select result → View metrics and charts

## Features

- View metrics (electricity, costs, CO₂, waste)
- Interactive charts with time controls
- CSV export for MATLAB

## Build

```bash
npm run build  # Output in dist/
```
