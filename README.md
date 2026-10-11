# SPARC - Simulation, Production Analysis & Refrigeration Control

This project contains a complete Docker Compose setup for the CONCAST Simulator application with Django backend, React frontend, and MariaDB database.

<img src="./logo/SPARC%20logo.png" alt="drawing" width="200"/>

## Prerequisites

- Docker Engine 20.10 or higher
- Docker Compose 2.0 or higher

## Quick Start

1. **Clone the repository**

2. **Configure environment variables**
   ```bash
   cp .compose.env.example .compose.env
   ```
   Edit `.env` and update the following:
   - `DJANGO_SECRET_KEY`: Generate a secure secret key
   - `DB_ROOT_PASSWORD`: Set a secure root password for MariaDB
   - `DB_PASSWORD`: Set a secure password for the application database user
   - `DEBUG`: Set to `True` for development, `False` for production

   ```bash
   source .compose.env
   ```

3. **Build and start the containers**
   ```bash
   docker-compose up -d --build
   ```

4. **Create a Django superuser** (first time only)
   ```bash
   docker-compose exec backend python manage.py createsuperuser
   ```

5. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000/api/
   - Admin Panel: http://localhost:8000/admin/
   - Database: localhost:3306


.dev.env is needed for local development without docker-compose.

## Architecture

The application consists of three main services:

### 1. Database (MariaDB)
- Container: `concast_db`
- Port: 3306
- Volume: `concast_mariadb_data` (persistent data storage)
- Healthcheck: Ensures database is ready before backend starts

### 2. Backend (Django)
- Container: `concast_backend`
- Port: 8000
- Framework: Django 4.2 with Django REST Framework
- WSGI Server: Gunicorn with 3 workers
- Volumes:
  - `media_files`: User-uploaded files
  - `static_files`: Static assets (CSS, JS, images)
- Features:
  - REST API for production simulations
  - Chiller optimization
  - Cost calculations
  - Admin interface

### 3. Frontend (React)
- Container: `concast_frontend`
- Port: 3000 (mapped to port 80 in container)
- Build: Multi-stage Docker build with Vite
- Server: Nginx
- Features:
  - Production simulations viewer
  - Chiller simulations viewer
  - Optimization results viewer
  - Interactive charts with Recharts



## Examples of file

Generation Dataset 
```csv
Time,cogen_kWh,solar_kWh
2024-01-01 00:00:00,0,0
2024-01-01 01:00:00,0,0
2024-01-01 02:00:00,0,0
...
```

Prices Dataset
```csv
Time,electricity_price,methane_prices
2024-01-01 00:00:00,0.18325,0.04958
2024-01-01 01:00:00,0.18025,0.04958
2024-01-01 02:00:00,0.17625,0.04958
2024-01-01 03:00:00,0.16195,0.04958
2024-01-01 04:00:00,0.16125,0.04958
````
In this CSV the methane_prices column could be left at 0 as it is not used in the current version of the simulator.



Temperature Dataset
```csv
Time,outside_temperature
2024-01-01 00:00:00,6.8
2024-01-01 01:00:00,5.9
2024-01-01 02:00:00,6.1
2024-01-01 03:00:00,5.5
2024-01-01 04:00:00,5.6
2024-01-01 05:00:00,4.7
2024-01-01 06:00:00,3.8
2024-01-01 07:00:00,3.5
```


Production Plan
```csv
Time,s_finit,s_torre,s_hiro,b_past,b_burr,b_conf
2025-09-22 00:00:00,1,0,0,0,0,0
2025-09-22 00:15:00,1,0,0,0,0,0
2025-09-22 00:30:00,1,0,0,0,0,0
2025-09-22 00:45:00,1,0,0,0,0,0
```

Each column represents a process. The values are either 0 or 1, indicating whether the process is inactive or active at that time.
The time intervals must be in 15-minute increments and they must go from a Monday to a Sunday (7 days).

## License

Copyright © 2025 CONCAST Simulator
