"""
Verification script:
1. Creates a database at pre-PR state with shipments.0006 applied.
2. Populates shipment tables with rows from cold-storage archive.
3. Proves row counts match the archive before deletion.
4. Runs normal django migrate (which applies shipments.0007).
5. Proves shipments.0007 records as applied in django_migrations.
6. Proves all 8 shipment tables are physically absent after migrate.
"""
import gc
import json
import os
import sys
import tempfile
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = Path(tempfile.gettempdir())
os.environ["DJANGO_SETTINGS_MODULE"] = "rate_engine.settings"
TEST_DB_PATH = TEMP_DIR / "rateengine_test_migration_upgrade.db"
TEST_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

import django

django.setup()

from django.core.management import call_command
from django.db import connection

COLD_STORAGE_ARCHIVE = Path("C:/Users/commercial.manager/dev/RateEngine-local-artifacts/cold_storage/archive_connotes_20260922.json")
if not COLD_STORAGE_ARCHIVE.exists():
    # Fallback check relative or docs
    COLD_STORAGE_ARCHIVE = BASE_DIR / "docs" / "archive" / "archive_connotes_20260922.json"

assert COLD_STORAGE_ARCHIVE.exists(), f"Archive file not found at {COLD_STORAGE_ARCHIVE}"

print("Step 1: Setting up full pre-PR database state with shipments at 0006...")
# Migrate all apps to full schema, then roll shipments back to 0006
call_command("migrate", verbosity=0)
call_command("migrate", "shipments", "0006_alter_shipmentevent_event_type", verbosity=0)

# Seed parent Organization and User referenced by the 32 shipment rows
from accounts.models import CustomUser
from parties.models import Organization

Organization.objects.get_or_create(
    id="1cff644f-3c53-470f-92ab-92bc3d649902",
    defaults={"name": "Test Org", "slug": "test-org"},
)
if not CustomUser.objects.filter(id=4).exists():
    CustomUser.objects.create(
        id=4,
        email="ops@example.com",
        first_name="Ops",
        last_name="User",
        role="operator",
    )

TABLE_MODEL_MAP = {
    "ShipmentSettings": "shipments_shipmentsettings",
    "ShipmentAddressBookEntry": "shipments_shipmentaddressbookentry",
    "ShipmentTemplate": "shipments_shipmenttemplate",
    "Shipment": "shipments_shipment",
    "ShipmentPiece": "shipments_shipmentpiece",
    "ShipmentCharge": "shipments_shipmentcharge",
    "ShipmentDocument": "shipments_shipmentdocument",
    "ShipmentEvent": "shipments_shipmentevent",
}

with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shipments_%'")
    existing_tables = {row[0] for row in cursor.fetchall()}

print(f"Verified {len(existing_tables)} shipment tables exist at 0006: {sorted(existing_tables)}")
assert len(existing_tables) == 8, f"Expected 8 shipment tables, found {len(existing_tables)}"

print("Step 2: Populating shipment tables from cold-storage archive...")
with open(COLD_STORAGE_ARCHIVE, "r", encoding="utf-8") as f:
    archive_data = json.load(f)

tables_data = archive_data["tables"]

# Disable foreign keys during archive data load
with connection.cursor() as cursor:
    cursor.execute("PRAGMA foreign_keys = OFF;")

# Insert in dependency order
insert_order = [
    "ShipmentSettings",
    "ShipmentAddressBookEntry",
    "ShipmentTemplate",
    "Shipment",
    "ShipmentPiece",
    "ShipmentCharge",
    "ShipmentDocument",
    "ShipmentEvent",
]

with connection.cursor() as cursor:
    for model_name in insert_order:
        tbl_name = TABLE_MODEL_MAP[model_name]
        cursor.execute(f'PRAGMA table_info("{tbl_name}")')
        table_cols = {col_info[1] for col_info in cursor.fetchall()}
        rows = tables_data[model_name]["rows"]
        for row in rows:
            db_row = {}
            for k, v in row.items():
                if k in table_cols:
                    db_row[k] = v
                elif f"{k}_id" in table_cols:
                    db_row[f"{k}_id"] = v
            cols = list(db_row.keys())
            vals = [
                json.dumps(db_row[c]) if isinstance(db_row[c], (dict, list)) else db_row[c]
                for c in cols
            ]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join([f'"{c}"' for c in cols])
            cursor.execute(f'INSERT INTO "{tbl_name}" ({col_names}) VALUES ({placeholders})', vals)

print("Step 3: Proving row counts match archive before deletion...")
pre_upgrade_counts = {}
with connection.cursor() as cursor:
    for model_name, tbl_name in TABLE_MODEL_MAP.items():
        cursor.execute(f'SELECT COUNT(*) FROM "{tbl_name}"')
        count = cursor.fetchone()[0]
        pre_upgrade_counts[model_name] = count
        expected = tables_data[model_name]["row_count"]
        assert count == expected, f"{model_name} expected {expected} rows, got {count}"
        print(f"  {model_name}: {count} rows (matches archive)")

total_pre_rows = sum(pre_upgrade_counts.values())
print(f"Total rows verified pre-upgrade: {total_pre_rows} (Expected 32)")
assert total_pre_rows == 32

print("Step 4: Running normal 'python backend/manage.py migrate'...")
call_command("migrate", verbosity=1)

print("Step 5: Proving shipments.0007_delete_shipment_models records as applied...")
with connection.cursor() as cursor:
    cursor.execute("SELECT app, name, applied FROM django_migrations WHERE app='shipments' AND name='0007_delete_shipment_models'")
    mig_record = cursor.fetchone()
    assert mig_record is not None, "shipments.0007_delete_shipment_models not found in django_migrations!"
    print(f"  Migration applied record: app={mig_record[0]}, name={mig_record[1]}, applied={mig_record[2]}")

print("Step 6: Proving all 8 shipment tables are physically absent...")
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shipments_%'")
    remaining_tables = [row[0] for row in cursor.fetchall()]

print(f"Remaining shipment tables: {remaining_tables}")
assert len(remaining_tables) == 0, f"Expected 0 shipment tables after 0007, found: {remaining_tables}"

print("=" * 60)
print("UPGRADE PATH VERIFICATION SUCCESSFUL!")
print("Pre-PR database at 0006 with 32 populated shipment rows upgraded to 0007.")
print("Migration shipments.0007 recorded as applied.")
print("All 8 shipment tables confirmed physically absent.")
print("=" * 60)

# Clean up test db
from django.db import connections

connections.close_all()
gc.collect()
TEST_DB_PATH.unlink(missing_ok=True)

print("Step 7: Proving fresh database migration from scratch...")
FRESH_DB_PATH = TEMP_DIR / "rateengine_test_fresh_db.sqlite3"
FRESH_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{FRESH_DB_PATH.as_posix()}"

connections.close_all()

call_command("migrate", verbosity=0)

fresh_conn = connections["default"]
with fresh_conn.cursor() as cursor:
    cursor.execute("SELECT app, name FROM django_migrations WHERE app='shipments' AND name='0007_delete_shipment_models'")
    fresh_mig = cursor.fetchone()
    assert fresh_mig is not None, "shipments.0007_delete_shipment_models not recorded in fresh database migrations!"

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shipments_%'")
    fresh_tables = [row[0] for row in cursor.fetchall()]
    assert len(fresh_tables) == 0, f"Expected 0 shipment tables on fresh db, got: {fresh_tables}"

connections.close_all()
gc.collect()
FRESH_DB_PATH.unlink(missing_ok=True)

print("FRESH DATABASE MIGRATION VERIFICATION SUCCESSFUL!")
print("Fresh database ran all migrations including shipments 0001-0007 with 0 shipment tables remaining.")
print("=" * 60)
