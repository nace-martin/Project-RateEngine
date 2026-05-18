#!/bin/sh
set -e

echo "Starting RateEngine Backend [Production Mode]"

# Collect static files (needed for WhiteNoise)
# In future phases, this may move to build time or a Cloud Run Job if using GCS.
echo "Collecting static files..."
python manage.py collectstatic --noinput

# DEPRECATED: Startup migrations are disabled to prevent race conditions in Cloud Run.
# Migrations will be handled via Cloud Run Jobs in Phase 5D.
echo "Skipping startup migrations (controlled by Phase 5B hardening)..."

# Support Cloud Run dynamic PORT variable, fallback to 8000 for local production testing
BIND_PORT=${PORT:-8000}
echo "Binding Gunicorn to port $BIND_PORT"

exec gunicorn rate_engine.wsgi:application \
    --bind 0.0.0.0:$BIND_PORT \
    --workers 4 \
    --threads 2 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
