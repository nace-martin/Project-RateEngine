#!/bin/sh
set -e

python manage.py collectstatic --noinput
python manage.py migrate --noinput

exec gunicorn rate_engine.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2 --access-logfile - --error-logfile -
