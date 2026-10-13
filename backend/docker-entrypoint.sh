#!/bin/sh
# Prepares the database, then starts the web server.
set -e

mkdir -p /data

# A random secret key, created on the first start and kept in the data volume
if [ -z "$DJANGO_SECRET_KEY" ]; then
    if [ ! -s /data/secret_key ]; then
        python -c "import secrets; print(secrets.token_urlsafe(50))" > /data/secret_key
    fi
    DJANGO_SECRET_KEY="$(cat /data/secret_key)"
    export DJANGO_SECRET_KEY
fi

python manage.py migrate --noinput
# Admin account and example data (only when the database is empty)
python manage.py setup_sparc

# Calculations run inside the web request: allow them up to 5 minutes
exec gunicorn simulator_project.wsgi:application \
    --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 300 --access-logfile -
