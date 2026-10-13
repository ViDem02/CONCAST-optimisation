FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code changes do not reinstall them
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Admin styles are collected once, when the image is built
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput --verbosity 0 \
    && chmod +x docker-entrypoint.sh

# Database and secret key live in the /data volume; the example data are mounted in /app/demo_data
ENV SQLITE_PATH=/data/sparc.sqlite3 \
    SECRET_KEY_FILE=/data/secret_key \
    SPARC_DEMO_DATA=/app/demo_data

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
