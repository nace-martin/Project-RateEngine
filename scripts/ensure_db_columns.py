import os
import sys

# Ensure backend is on sys.path regardless of where this script is invoked from
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

import django

django.setup()

from django.db import connection


def main():
    with connection.cursor() as cur:
        # Ensure new columns are present on unmanaged tables in case migrations were skipped
        cur.execute(
            "ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS commodity_code VARCHAR(8) DEFAULT 'GCR'"
        )
        cur.execute(
            "ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS rate_strategy VARCHAR(32) DEFAULT 'BREAKS'"
        )
        cur.execute(
            "ALTER TABLE routes ADD COLUMN IF NOT EXISTS requires_manual_rate BOOLEAN DEFAULT FALSE"
        )
        cur.execute(
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS country_code CHAR(2) DEFAULT 'PG'"
        )
    print("Columns ensured on ratecards and routes.")


if __name__ == "__main__":
    main()
