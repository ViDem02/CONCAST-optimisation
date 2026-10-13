@echo off
rem Starts SPARC and opens it in the browser. Double-click this file.
cd /d "%~dp0"
set PORT=3000
if exist .env for /f "tokens=2 delims==" %%p in ('findstr /b "SPARC_PORT=" .env') do set PORT=%%p
set URL=http://localhost:%PORT%

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/
  echo then double-click this file again.
  start "" https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Starting Docker Desktop...
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  for /l %%i in (1,1,90) do (
    docker info >nul 2>nul && goto docker_ready
    timeout /t 2 /nobreak >nul
  )
  echo Docker Desktop did not start. Open it by hand, wait until it says it is running, then try again.
  pause
  exit /b 1
)
:docker_ready

echo Starting SPARC (the very first time this takes a few minutes)...
docker compose up -d --build
if errorlevel 1 (
  echo SPARC could not be started: see the messages above.
  pause
  exit /b 1
)

echo Waiting for SPARC to answer...
for /l %%i in (1,1,120) do (
  curl -fs -o nul %URL%/admin/login/ && goto sparc_ready
  timeout /t 1 /nobreak >nul
)
:sparc_ready

echo.
echo SPARC is running at %URL%
echo Log in with the user "admin" and the password "sparc" (unless you changed them).
start "" %URL%
echo You can close this window: SPARC keeps running until you use stop.bat or shut down Docker.
pause
