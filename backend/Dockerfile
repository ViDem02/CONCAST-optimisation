FROM python:3.11-slim

WORKDIR /app

# Create media directory with correct permissions
RUN mkdir -p /app/media && chmod 755 /app/media

# Install system dependencies for mysqlclient and locales
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Generate Italian locale
RUN sed -i '/it_IT.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen it_IT.UTF-8

# Set environment variables
ENV LANG=it_IT.UTF-8
ENV LANGUAGE=it_IT:it
ENV LC_ALL=it_IT.UTF-8
ENV PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

EXPOSE 8000

# Command will be overridden by docker-compose
CMD ["gunicorn", "simulator_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
