# CONCAST Simulator - Frontend

React frontend for viewing simulation results.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`

## Prerequisites

- Node.js 18+
- Django backend at `http://localhost:8000` (the Vite dev server proxies `/api` and `/admin` to it)
- A Django user account: the API requires login, and the app redirects to `/admin/login/` when you are not logged in

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
