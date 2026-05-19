#!/bin/sh
set -e

echo "Starting RateEngine Database Migrations [Production Mode]"

# Collect static files is usually done in the build stage or web service entrypoint,
# but for the migration job we focus purely on the DB.

# Run migrations
echo "Running python manage.py migrate..."
python manage.py migrate --noinput

echo "Migrations completed successfully."
