#!/bin/bash
# Stops SPARC. Your data are kept and will be there at the next start.
cd "$(dirname "$0")" || exit 1
docker compose stop && echo "SPARC is stopped. Your data are kept."
echo; read -r -p "Press Enter to close this window." _
