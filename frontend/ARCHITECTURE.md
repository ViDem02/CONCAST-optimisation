# Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CONCAST Simulator                            │
│                    Calculation of Costs & Usage                      │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                             │
│                      http://localhost:3000                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Navigation Bar                          │   │
│  │  [CONCAST Simulator] | Simulations | New Simulation | Results│  │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Main Content                            │   │
│  │                                                              │   │
│  │  Route: /                                                    │   │
│  │  ┌─────────────────────────────────────────────────┐        │   │
│  │  │        SimulationList Component                 │        │   │
│  │  │  - Grid of simulation cards                     │        │   │
│  │  │  - View & Delete actions                        │        │   │
│  │  └─────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  Route: /create                                              │   │
│  │  ┌─────────────────────────────────────────────────┐        │   │
│  │  │       CreateSimulation Component                │        │   │
│  │  │  - Form with validation                         │        │   │
│  │  │  - Production plan dropdown                     │        │   │
│  │  │  - Date range selection                         │        │   │
│  │  └─────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  Route: /simulation/:id                                      │   │
│  │  ┌─────────────────────────────────────────────────┐        │   │
│  │  │      SimulationDetail Component                 │        │   │
│  │  │  - Simulation information                       │        │   │
│  │  │  - Production processes table                   │        │   │
│  │  │  - "Run Simulation" button                      │        │   │
│  │  └─────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  Route: /results/:id                                         │   │
│  │  ┌─────────────────────────────────────────────────┐        │   │
│  │  │         ResultsView Component                   │        │   │
│  │  │  ┌────────────────────────────────────────┐     │        │   │
│  │  │  │   Summary Cards (8 metrics)            │     │        │   │
│  │  │  │   ⚡ 🔌 ☀️ 🏭 💰 ♻️ 🌍 ⏱️               │     │        │   │
│  │  │  └────────────────────────────────────────┘     │        │   │
│  │  │  ┌────────────────────────────────────────┐     │        │   │
│  │  │  │      ResultsCharts Component           │     │        │   │
│  │  │  │  - Electricity Flow (Area)             │     │        │   │
│  │  │  │  - Generation Sources (Line)           │     │        │   │
│  │  │  │  - Grid Costs (Bar)                    │     │        │   │
│  │  │  │  - Wasted Energy (Area)                │     │        │   │
│  │  │  │  - Time resolution controls            │     │        │   │
│  │  │  └────────────────────────────────────────┘     │        │   │
│  │  └─────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    API Service Layer                         │   │
│  │                    (services/api.js)                         │   │
│  │                                                              │   │
│  │  - simulationApi: CRUD + run()                               │   │
│  │  - resultsApi: get + export CSV                              │   │
│  │  - productionPlanApi: list                                   │   │
│  │  - processApi: list by plan                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                    ↕
                          HTTP Requests (JSON/CSV)
                         Proxy: /api → :8000/api
                                    ↕
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND (Django)                             │
│                     http://localhost:8000                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Django REST API                           │   │
│  │                                                              │   │
│  │  /api/planning/simulations/                                  │   │
│  │    GET, POST, PUT, DELETE                                    │   │
│  │    POST /{id}/run/  → Run simulation                         │   │
│  │                                                              │   │
│  │  /api/simulation/simulation-results/                         │   │
│  │    GET /{id}/                                                │   │
│  │    GET /{id}/?include_timestep_data=true                     │   │
│  │    GET /{id}/export-csv/  → Download CSV                     │   │
│  │                                                              │   │
│  │  /api/planning/weekly-production-plans/                      │   │
│  │    GET - List all plans                                      │   │
│  │                                                              │   │
│  │  /api/planning/processes/                                    │   │
│  │    GET ?production_plan={id}                                 │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Business Logic Layer                        │   │
│  │                                                              │   │
│  │  SimulationApp/simulation.py:                                │   │
│  │    - run_simulation()                                        │   │
│  │    - retime_hourly_to_5min()                                 │   │
│  │    - build_production_matrix()                               │   │
│  │    - calculate_electricity_demand()                          │   │
│  │    - validate datasets                                       │   │
│  │                                                              │   │
│  │  SimulationApp/utils.py:                                     │   │
│  │    - export_simulation_results_to_csv()                      │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Data Layer                              │   │
│  │                                                              │   │
│  │  Models:                                                     │   │
│  │    - Simulation (PlanningApp)                                │   │
│  │    - SimulationResults (SimulationApp)                       │   │
│  │    - WeeklyProductionPlan (PlanningApp)                      │   │
│  │    - Process (PlanningApp)                                   │   │
│  │    - Shift (PlanningApp)                                     │   │
│  │    - GenerationDataset (DatasetApp)                          │   │
│  │    - PricesDataset (DatasetApp)                              │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Database (SQLite/MySQL)                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘


                         DATA FLOW EXAMPLE
                    (Run Simulation Use Case)

┌──────────────────┐                                    ┌────────────────┐
│                  │  1. Click "Run Simulation"         │                │
│  SimulationDetail├───────────────────────────────────►│  Django API    │
│  Component       │                                    │  /run/         │
│                  │                                    │                │
└──────────────────┘                                    └────────┬───────┘
                                                                 │
                                                                 │ 2. Call
                                                                 ↓
                                                      ┌────────────────┐
                                                      │ run_simulation │
                                                      │   function     │
                                                      │                │
                                                      │ • Validate     │
                                                      │ • Retime data  │
                                                      │ • Calculate    │
                                                      │ • Save results │
                                                      └────────┬───────┘
                                                               │
                                                               │ 3. Return
                                                               ↓
┌────────────────┐                                    ┌──────────────────┐
│                │  4. Navigate to results            │                  │
│  ResultsView   │◄───────────────────────────────────┤ SimulationResults│
│  Component     │                                    │   (JSON)         │
│                │                                    │                  │
└────────┬───────┘                                    └──────────────────┘
         │
         │ 5. Display metrics
         ↓
┌────────────────┐
│ Summary Cards  │
│ • 8 Metrics    │
└────────────────┘
         │
         │ 6. Render charts
         ↓
┌────────────────┐
│ ResultsCharts  │
│ • 4 Chart types│
│ • Interactive  │
└────────────────┘


                         TECHNOLOGY STACK

Frontend:
  ├─ React 18.2          - UI library
  ├─ React Router 6.20   - Client-side routing
  ├─ Axios 1.6           - HTTP client
  ├─ Recharts 2.10       - Data visualization
  ├─ date-fns 2.30       - Date utilities
  └─ Vite 5.0            - Build tool

Backend:
  ├─ Django 4.2+         - Web framework
  ├─ DRF 3.14+           - REST API
  ├─ django-cors 4.3+    - Cross-origin support
  ├─ django-filter 23.2+ - API filtering
  └─ PyYAML 6.0+         - YAML parsing

Database:
  └─ SQLite (dev) / MySQL (prod)


                     DEPLOYMENT ARCHITECTURE

Development:
  Frontend: http://localhost:3000 (Vite dev server)
  Backend:  http://localhost:8000 (Django runserver)
  Proxy:    /api → http://localhost:8000/api

Production Option 1 (Separate):
  Frontend: CDN / Static hosting
  Backend:  Application server
  CORS:     Configured for frontend domain

Production Option 2 (Integrated):
  Django serves React build from staticfiles
  Single domain deployment
  No CORS configuration needed
