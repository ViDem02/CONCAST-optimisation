#!/bin/bash
# Starts SPARC and opens it in the browser. On a Mac: double-click this file.
# On Linux: run ./start.command
cd "$(dirname "$0")" || exit 1

PORT=$(grep -s '^SPARC_PORT=' .env | cut -d= -f2)
URL="http://localhost:${PORT:-3000}"

pause_and_exit() { echo; read -r -p "Press Enter to close this window." _; exit "$1"; }

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/"
    echo "then double-click this file again."
    [ "$(uname)" = "Darwin" ] && open "https://www.docker.com/products/docker-desktop/"
    pause_and_exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Starting Docker Desktop..."
    [ "$(uname)" = "Darwin" ] && open -a Docker
    for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
    if ! docker info >/dev/null 2>&1; then
        echo "Docker Desktop did not start. Open it by hand, wait until it says it is running, then try again."
        pause_and_exit 1
    fi
fi

echo "Starting SPARC (the very first time this takes a few minutes)..."
if ! docker compose up -d --build; then
    echo "SPARC could not be started: see the messages above."
    pause_and_exit 1
fi

echo "Waiting for SPARC to answer..."
for _ in $(seq 1 120); do
    curl -fs -o /dev/null "$URL/admin/login/" && break
    sleep 1
done

echo
echo "SPARC is running at $URL"
echo "Log in with the user \"admin\" and the password \"sparc\" (unless you changed them)."
if [ "$(uname)" = "Darwin" ]; then open "$URL"; else xdg-open "$URL" >/dev/null 2>&1 || true; fi
echo "You can close this window: SPARC keeps running until you use stop.command or shut down Docker."
pause_and_exit 0
