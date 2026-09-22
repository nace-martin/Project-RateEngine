import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
PRE_DB = BACKEND_DIR / "db_pre_cleanup.sqlite3"
TEST_UPGRADED_DB = BACKEND_DIR / "test_upgraded_crm.sqlite3"

print("=" * 60)
print("TEST 1: Existing DB Upgrade Proof from pre-cleanup state")
print("=" * 60)

assert PRE_DB.exists(), f"Pre-cleanup DB copy not found at {PRE_DB}"
if TEST_UPGRADED_DB.exists():
    TEST_UPGRADED_DB.unlink()

shutil.copyfile(PRE_DB, TEST_UPGRADED_DB)

# 1. Confirm pre-cleanup state and row counts
conn = sqlite3.connect(TEST_UPGRADED_DB)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'crm_%' ORDER BY name").fetchall()]
print(f"Pre-migration CRM tables: {tables}")
assert len(tables) == 3, f"Expected 3 tables, got {len(tables)}"

counts = {}
for t in tables:
    cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    counts[t] = cnt
    print(f"  {t}: {cnt} rows")

assert counts["crm_opportunity"] == 88, f"Expected 88 opportunities, got {counts['crm_opportunity']}"
assert counts["crm_interaction"] == 259, f"Expected 259 interactions, got {counts['crm_interaction']}"
assert counts["crm_task"] == 0, f"Expected 0 tasks, got {counts['crm_task']}"
total_rows = sum(counts.values())
print(f"Total verified CRM rows: {total_rows} (Expected 347)")

cols = [r[1] for r in cur.execute("PRAGMA table_info(quotes_quote)").fetchall()]
assert "opportunity_id" in cols, "Expected opportunity_id in quotes_quote"
print("Pre-migration quotes_quote has opportunity_id FK column: True")
conn.close()

# 2. Run normal manage.py migrate
print("\nRunning 'python manage.py migrate' on existing database...")
env = os.environ.copy()
env["DATABASE_URL"] = f"sqlite:///{TEST_UPGRADED_DB.as_posix()}"
res = subprocess.run(
    [sys.executable, str(BACKEND_DIR / "manage.py"), "migrate"],
    cwd=str(BACKEND_DIR),
    env=env,
    capture_output=True,
    text=True,
)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
assert res.returncode == 0, f"Migration failed with exit code {res.returncode}"

# 3. Confirm deletion migration recorded
conn = sqlite3.connect(TEST_UPGRADED_DB)
cur = conn.cursor()
cur.execute("SELECT app, name, applied FROM django_migrations WHERE (app='quotes' AND name='0050_remove_quote_opportunity') OR (app='crm' AND name='0004_delete_crm_models') ORDER BY id")
records = cur.fetchall()
print("Applied cleanup migrations:")
for r in records:
    print(f"  {r[0]}.{r[1]} (applied at {r[2]})")
assert len(records) == 2, f"Expected 2 migration records, got {len(records)}"

# 4. Confirm all CRM tables physically absent
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'crm_%'")
remaining = [r[0] for r in cur.fetchall()]
print(f"Post-migration CRM tables: {remaining}")
assert len(remaining) == 0, f"Expected 0 CRM tables, found {remaining}"

# 5. Confirm Quote schema no longer has CRM FK
post_cols = [r[1] for r in cur.execute("PRAGMA table_info(quotes_quote)").fetchall()]
print(f"opportunity_id in quotes_quote post-migration: {'opportunity_id' in post_cols}")
assert "opportunity_id" not in post_cols, "opportunity_id should not exist in quotes_quote"
conn.close()

# 6. Test quote creation on upgraded db
print("\nTesting Quote creation on upgraded DB...")
quote_test = subprocess.run(
    [sys.executable, "-c", """
import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'rate_engine.settings'
django.setup()
from quotes.models import Quote
from parties.models import Company
from core.models import Location
from accounts.models import CustomUser

user = CustomUser.objects.first()
comp = Company.objects.filter(is_customer=True).first()
orig = Location.objects.first()
dest = Location.objects.last()

q = Quote.objects.create(
    quote_number='Q-TEST-UPGRADED-999',
    customer=comp,
    mode='AIR',
    incoterm='D2D',
    service_scope='D2D',
    payment_term='PREPAID',
    origin_location=orig,
    destination_location=dest,
    created_by=user,
    status='DRAFT',
)
print('Successfully created Quote:', q.quote_number, 'id:', q.id)
assert not hasattr(q, 'opportunity_id') or q.opportunity_id is None
"""],
    cwd=str(BACKEND_DIR),
    env=env,
    capture_output=True,
    text=True,
)
print(quote_test.stdout)
if quote_test.stderr:
    print("STDERR:", quote_test.stderr)
assert quote_test.returncode == 0, "Quote creation failed"

print("=" * 60)
print("TEST 1 PASSED: Real upgrade from pre-cleanup state to Wave 2B successfully verified!")
print("=" * 60)

# Clean up
if TEST_UPGRADED_DB.exists():
    TEST_UPGRADED_DB.unlink()

print("\n" + "=" * 60)
print("TEST 2: Fresh SQLite Database Migration from Scratch")
print("=" * 60)
FRESH_DB = BACKEND_DIR / "test_fresh_crm.sqlite3"
if FRESH_DB.exists():
    FRESH_DB.unlink()

fresh_env = os.environ.copy()
fresh_env["DATABASE_URL"] = f"sqlite:///{FRESH_DB.as_posix()}"
res_fresh = subprocess.run(
    [sys.executable, str(BACKEND_DIR / "manage.py"), "migrate"],
    cwd=str(BACKEND_DIR),
    env=fresh_env,
    capture_output=True,
    text=True,
)
assert res_fresh.returncode == 0, f"Fresh migrate failed: {res_fresh.stderr}"

conn = sqlite3.connect(FRESH_DB)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'crm_%'")
fresh_crm_tables = [r[0] for r in cur.fetchall()]
print(f"Fresh DB CRM tables: {fresh_crm_tables}")
assert len(fresh_crm_tables) == 0

cur.execute("PRAGMA table_info(quotes_quote)")
fresh_quote_cols = [r[1] for r in cur.execute("PRAGMA table_info(quotes_quote)").fetchall()]
assert "opportunity_id" not in fresh_quote_cols
conn.close()

if FRESH_DB.exists():
    FRESH_DB.unlink()

print("=" * 60)
print("TEST 2 PASSED: Fresh SQLite database ran all migrations cleanly with 0 CRM tables and no Quote.opportunity FK!")
print("=" * 60)
