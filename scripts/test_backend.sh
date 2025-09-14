#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

# Default DATABASE_URL if not set
export DATABASE_URL="${DATABASE_URL:-postgres://rateengine:rateengine@127.0.0.1:5432/rateengine}"

if ! command -v python >/dev/null 2>&1; then
  echo "Python not found in PATH. Activate your venv first." >&2
  exit 1
fi

echo "Running migrations ..."
python manage.py migrate

echo "Running tests ..."
python manage.py test -v 2

