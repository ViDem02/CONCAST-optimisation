@echo off
rem Stops SPARC. Your data are kept and will be there at the next start.
cd /d "%~dp0"
docker compose stop
if not errorlevel 1 echo SPARC is stopped. Your data are kept.
pause
