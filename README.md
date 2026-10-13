# SPARC - Simulation, Production Analysis & Refrigeration Control

<img src="./logo/SPARC%20logo.png" alt="SPARC logo" width="200"/>

SPARC helps CONCAST buy less electricity from the grid. It moves the flexible production shifts
(within the minutes each shift is allowed to move) to the hours when the solar panels and the
cogenerator produce, or when electricity is cheaper, and shows how much this saves. It also
simulates cold rooms that cool with the surplus on-site production.

## Start SPARC (no technical knowledge needed)

1. Install **Docker Desktop** once: <https://www.docker.com/products/docker-desktop/> (check its
   licence terms with IT: it is free only for smaller companies; on a Linux server the free Docker
   Engine works too).
2. Download this folder (on GitHub: green "Code" button → "Download ZIP", then unzip it).
3. Double-click:
   - **Mac**: `start.command` (the first time, right-click → Open, then confirm);
   - **Windows**: `start.bat`;
   - **Linux**: run `./start.command` in a terminal.
4. Your browser opens <http://localhost:3000>. Log in with user **admin**, password **sparc**,
   then change the password (top right of the "Manage data" pages: "Change password").

The very first start prepares SPARC and takes a few minutes; afterwards it starts in seconds.
The CONCAST data (generation, prices, temperatures and the reference production week) are
already loaded, with one example optimisation and one example cost simulation.

To stop SPARC, double-click `stop.command` (Mac) or `stop.bat` (Windows). Your data are kept
between starts.

## Using SPARC

The website has two parts:

- **Results** (<http://localhost:3000>): the home page explains the steps; *Optimisations*,
  *Cost simulations* and *Cold rooms* show results and charts; *Production plans* shows each
  week as a chart. Items that are not calculated yet have a **Calculate now** button.
- **Manage data** (<http://localhost:3000/admin/>): where data are uploaded and calculations are
  set up. Every calculation page has a **Save and calculate** button; the result appears on the
  same page, with a link to its charts.

The usual workflow:

1. **Input data**: upload hourly CSV files (on-site generation, electricity prices, outside
   temperature). The upload page shows the expected columns and checks the file; the list shows
   which dates each dataset covers.
2. **Production plans**: import a week from a CSV timetable and a YAML file ("Import from CSV +
   YAML"), then, per process, set how many minutes each shift may start earlier or later.
3. **Shift optimisation**: choose a plan, the Monday of a reference week and the data, then
   *Save and optimise*. A new plan with the moved shifts is created.
4. **Cost simulation**: compare the current and the optimised plan over a longer period (the
   optimisation page has a link that pre-fills it). This shows whether the savings found on one
   week hold on the others.

### File formats

Hourly data (one row per hour, no missing hours):

```csv
Time,cogen_kWh,solar_kWh
2024-01-01 00:00:00,350,0
```
```csv
Time,electricity_price
2024-01-01 00:00:00,0.18325
```
```csv
Time,outside_temperature
2024-01-01 00:00:00,6.8
```

Production plan: a CSV timetable with one 0/1 column per process, one row every 15 minutes from
Monday 00:00 to Sunday 23:45, and a YAML file with the power and allowed movement of each process
(see `data/production_timetable.csv` and `data/production.yaml`).

## Settings

Optional settings go in a file called `.env` next to `docker-compose.yml` (copy `.env.example`):
the port (default 3000), whether other computers of the network may open SPARC (default: only
this computer) and the first login. To start again from an empty database with the example data,
run `docker compose down -v` and start SPARC again (this deletes everything entered).

## For developers

- `docker-compose.yml` runs two containers: **backend** (Django 5.2 + Django REST Framework,
  Gunicorn, SQLite database in the `sparc_data` volume) and **frontend** (React + Vite, served
  by nginx, which also forwards `/api`, `/admin` and `/static` to the backend). Only the frontend
  port is published.
- On every start the backend applies the migrations and runs `manage.py setup_sparc`, which
  creates the first login and, when the database is empty, loads `data/` and calculates the
  examples.
- Backend documentation: [backend/README.md](backend/README.md). Frontend: [frontend/README.md](frontend/README.md).
- Tests: `cd backend && DJANGO_SECRET_KEY=dev DEBUG=True python manage.py test`.
- Local development without Docker: `.dev.env.example` (backend on port 8000, `npm run dev` for
  the frontend on port 3000, which proxies the backend; set `FRONTEND_URL=http://localhost:3000`
  so that the admin links to the charts).

## License

Copyright © 2025 CONCAST Simulator
