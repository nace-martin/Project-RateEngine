#!/usr/bin/env bash
set -euo pipefail

# Start Postgres via Docker Compose and print DATABASE_URL helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

echo "Starting Postgres (docker-compose) ..."
docker compose up -d postgres

DB_URL="postgres://rateengine:rateengine@127.0.0.1:5432/rateengine"
echo "Postgres started. Use this in your shell:"
echo "  export DATABASE_URL=$DB_URL"

