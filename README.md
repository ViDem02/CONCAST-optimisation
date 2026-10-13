# SPARC — Simulation, Production Analysis & Refrigeration Control

<img src="./logo/SPARC%20logo.png" alt="SPARC logo" width="180"/>

SPARC helps CONCAST buy less electricity from the grid. It moves the flexible production batches,
within the time each batch is allowed to move, to the hours when the cogenerator and the solar
panels produce or when grid electricity is cheaper. It then shows what the new timetable saves over
any period. It also simulates a cold room that cools with the surplus on-site production.

On the CONCAST data (January 2024 – October 2025), optimising every week with that week's
generation and prices saves about **€4,600 per year** (2.1% of the grid electricity cost), or about
**€5,100** with the planned FV3 solar plant. The saving is reached only if the timetable is
re-optimised every week with the expected generation and prices of the coming week. Details are in
the [industrial report](report/sparc_industrial_report.pdf).

**Contents:**
[What SPARC does](#what-sparc-does) ·
[Start SPARC](#start-sparc) ·
[Using SPARC](#using-sparc) ·
[Input data](#input-data) ·
[Settings](#settings) ·
[Maintenance](#maintenance) ·
[Troubleshooting](#troubleshooting) ·
[For developers](#for-developers)

## What SPARC does

| Function | What it answers |
| --- | --- |
| **Shift optimisation** | For a weekly production plan and a reference week: what is the cheapest start time of each flexible batch? The result is saved as a new plan. |
| **Cost simulation** | What does a plan cost in grid electricity over a week, a month or a season, alone or compared with another plan? |
| **Cold-room simulation** (pilot) | How does a cold room behave when it is cooled with on-site production first, pre-cooling when there is surplus? |

### How the optimisation works

- The week is divided into 5-minute steps. Each process runs at constant power while it is on.
  Each block of activity of a process (a *run*) may start earlier or later within the limits of its
  shift.
- SPARC chooses one start time per run so that the cost of the electricity bought from the grid is
  as low as possible. At every step, production first uses the on-site generation, and only the rest
  is bought at that hour's price.
- The rules are always respected:
  - a run keeps its length and power;
  - fixed runs never move;
  - two runs of the same process never overlap.
- The weekly plan repeats every week, so the week is treated as **periodic**. A batch moved past
  Sunday 24:00 continues on Monday 00:00, and a batch crossing midnight on Sunday is one batch.
  Moving batches never adds or removes energy; the tool checks this before it saves a plan.
- The problem is solved exactly as a mixed-integer linear programme (MILP) with the open-source
  HiGHS solver. A week takes 1–2 seconds and is proven to be within 0.01% of the best possible cost.
- Before calculating, SPARC checks that the generation and the prices have a valid value for
  **every hour** of the period. A missing hour is never treated as zero.

## Start SPARC

No technical knowledge is needed.

1. Install **Docker Desktop** once from <https://www.docker.com/products/docker-desktop/>.
   Check its licence with IT: it is free only for smaller companies. On a Linux server the free
   Docker Engine works too.
2. Download this folder: on GitHub, use the green **Code** button, then **Download ZIP**, and unzip
   it.
3. Double-click the start file:
   - **Mac:** `start.command` (the first time: right-click, **Open**, then confirm);
   - **Windows:** `start.bat`;
   - **Linux:** run `./start.command` in a terminal.
4. The browser opens <http://localhost:3000>. Log in with user **admin** and password **sparc**,
   then change the password (in **Manage data**, top right: **Change password**).

The very first start prepares SPARC and takes a few minutes; after that it starts in a few
seconds. The CONCAST data are already loaded: generation with and without FV3, prices for 2024–2025,
Trento temperatures and the reference production week. One example optimisation and one example
cost simulation are already calculated.

To stop SPARC, double-click `stop.command` (Mac) or `stop.bat` (Windows). Your data are kept for
the next start.

## Using SPARC

The website has two areas:

- **Results** (<http://localhost:3000>): the home page explains the steps. *Optimisations*,
  *Cost simulations* and *Cold rooms* show the results with charts; *Production plans* shows each
  week as a chart. Anything not yet calculated has a **Calculate now** button.
- **Manage data** (<http://localhost:3000/admin/>): where data are uploaded and calculations are
  set up. Every calculation has a **Save and calculate** button. The result appears on the same
  page, with a link to its charts. Changing a setting removes the old result, so an outdated figure
  is never shown.

While an optimisation runs, the website and the admin page show its live progress: which step is
running (checking the data, building the model, searching for the cheapest timetable, writing the
plan), the size of the problem and the time spent. The page updates by itself when the result is
ready.

The usual workflow:

1. **Input data:** upload the hourly CSV files. The upload page checks the file and the list shows
   which dates each dataset covers.
2. **Production plan:** import a typical week (**Import from CSV + YAML**). Then, for each shift,
   set how many minutes it may start earlier or later (0 = fixed).
3. **Shift optimisation:** choose the plan, the Monday of a reference week and the data, then
   **Save and optimise**. A new plan with the moved shifts is created.
4. **Cost simulation:** compare the current and the optimised plan over a longer period. The
   optimisation page has a link that fills in the form. This checks whether the saving found on one
   week holds on the others.

**Recommended routine:** every week, optimise the coming week with the expected prices and
generation, and have production planning review the moved batches. SPARC does not yet know about
the order between processes, cleaning times or staff. After the week, run a cost simulation with the
actual data to track the real saving.

## Input data

Hourly data have one row per hour, and no hour may be missing. Times are local (Europe/Rome).

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

- Generation is the kWh produced in the hour; prices are in €/kWh.
- Values must be numbers. Generation and prices cannot be negative.
- Files are checked before anything is saved; an error names the line to fix.
- Extra columns (such as the old `methane_prices`) are ignored.
- The hour repeated when the clocks go back in October cannot be written in a local-time file. It
  takes the value of the hour before.

A **production plan** has two files:

- a CSV timetable with a `Time` column and one 0/1 column per process, one row every 15 minutes
  from Monday 00:00 to Sunday 23:45;
- a YAML file with, for each process, its power in kW (`electricity_consumption_kWh`) and how far
  its shifts may move (`max_forward_minutes`, `max_backwards_minutes`).

See `data/production_timetable.csv` and `data/production.yaml`.

## Settings

Optional. Copy `.env.example` to `.env` next to `docker-compose.yml` and change what you need, then
start SPARC again.

| Setting | Default | Meaning |
| --- | --- | --- |
| `SPARC_PORT` | `3000` | Port of the website (<http://localhost:3000>) |
| `SPARC_HOST` | `127.0.0.1` | `127.0.0.1`: only this computer can open SPARC. `0.0.0.0`: every computer of the network (change the admin password first). |
| `SPARC_ADMIN_USER`, `SPARC_ADMIN_PASSWORD` | `admin`, `sparc` | Login created on the very first start |
| `USE_HTTPS` | `False` | `True` only when SPARC is served over HTTPS |

## Maintenance

Run these commands in a terminal, in the SPARC folder.

| Task | Command |
| --- | --- |
| Back up the data | `docker compose stop backend`, then `docker compose cp backend:/data/sparc.sqlite3 sparc-backup.sqlite3`, then `docker compose start backend` |
| Restore a backup | `docker compose stop backend`, then `docker compose cp sparc-backup.sqlite3 backend:/data/sparc.sqlite3`, then `docker compose start backend` |
| Change a forgotten password | `docker compose exec backend python manage.py changepassword admin` |
| Install a new version | Replace the folder (or `git pull`), then start SPARC again: the data are kept and updated automatically |
| Start again from scratch | `docker compose down -v`, then start SPARC: **this deletes everything entered** and reloads the example data |

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The start window says Docker is not running | Open Docker Desktop, wait until it says it is running, then start SPARC again. |
| "port is already allocated" | Another program uses port 3000: set `SPARC_PORT=3001` in `.env` (see [Settings](#settings)). |
| "… have no value for N hour(s) of the period" | The data do not cover the chosen dates: upload the missing hours or choose dates inside the data. The list of datasets shows the dates covered. |
| A calculation fails with another message | The message is shown on the page. For more detail: `docker compose logs backend`. |

## For developers

### Architecture

`docker-compose.yml` runs two containers:

- **backend:** Django 5.2 and Django REST Framework, served by Gunicorn, with a SQLite database
  in the `sparc_data` volume;
- **frontend:** React and Vite, served by nginx, which also forwards `/api`, `/admin` and
  `/static` to the backend.

Only the frontend port is published. On every start the backend applies the migrations and runs
`manage.py setup_sparc`. That command creates the first login and, on an empty database, loads
`data/` and calculates the examples. The secret key is generated on the first start and kept in the
volume.

```
backend/
  DatasetApp/       hourly datasets, CSV import, validated hourly series (series.py)
  PlanningApp/      production plans, shifts, plan import, cost simulations
  OptimizerApp/     optimisation: packager (database ↔ problem) and optimizers/ (MILP, legacy heuristic)
  SimulationApp/    cost simulation engine and its results
  ChillersApp/      cold-room simulation (pilot)
  Bootstrap/        first-start setup
frontend/           React website
data/               CONCAST data loaded on the first start
report/             industrial report (PDF + LaTeX) and analysis/ scripts behind its figures
start.*, stop.*     launchers for Mac, Linux and Windows
```

### Development without Docker

Use `.dev.env.example` for the settings. Run the backend with `python manage.py runserver` on port
8000, and `npm run dev` in `frontend/` on port 3000; the dev server proxies the backend. Set
`FRONTEND_URL=http://localhost:3000` so that the admin links to the charts. See
[backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md).

### Tests

```bash
cd backend
DJANGO_SECRET_KEY=dev DEBUG=True python manage.py test
```

There are 97 tests (about 15 s). They cover:

- **Optimisation:** each rule of the model on an instance with a known answer, optimality against
  brute-force enumeration on random instances, and the solver fallbacks.
- **Energy conservation:** every move, every MILP candidate and every saved plan uses exactly the
  energy of the original plan, including batches moved across Sunday/Monday.
- **Data checks:** missing, infinite or negative values stop a calculation before the solver
  runs.
- **Live progress:** steps reported in order, background runs, refused double starts, runs
  interrupted by a restart.
- **Whole pipeline:** database → optimised plan → cost simulation of that plan, which must
  reproduce the optimiser's costs.
- **First start:** with the real data, including every admin page and the API.

### Analysis

[report/analysis](report/analysis/README.md) contains the scripts that produced the figures of the
industrial report: all 92 weeks of 2024–2025 for both generation scenarios, ways of reusing a
plan, and the width of the movement window. They rebuild the problem from `data/` without Django.

## License

Copyright © 2025 CONCAST Simulator
