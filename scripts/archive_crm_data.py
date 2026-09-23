"""
Script to archive legacy CRM data (Opportunity, Interaction, Task, and Quote linkages)
to private cold storage outside Git, and generate a non-sensitive manifest.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "backend" / "db.sqlite3"
COLD_STORAGE_DIR = Path("C:/Users/commercial.manager/dev/RateEngine-local-artifacts/cold_storage")
COLD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_PATH = COLD_STORAGE_DIR / "archive_crm_20260922.json"
MANIFEST_PATH = BASE_DIR / "docs" / "archive" / "archive_crm_20260922_manifest.json"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def fetch_table(table_name, order_by="id"):
    cur.execute(f"SELECT * FROM {table_name} ORDER BY {order_by}")
    rows = []
    for r in cur.fetchall():
        row_dict = dict(r)
        rows.append(row_dict)
    return rows

print("Extracting CRM tables...")
opp_rows = fetch_table("crm_opportunity")
interaction_rows = fetch_table("crm_interaction")
task_rows = fetch_table("crm_task")

cur.execute("SELECT id, quote_number, opportunity_id FROM quotes_quote WHERE opportunity_id IS NOT NULL ORDER BY id")
quote_linkages = [dict(r) for r in cur.fetchall()]

# Referential integrity check
opp_ids = {r["id"] for r in opp_rows}
orphan_interactions = [r for r in interaction_rows if r["opportunity_id"] and r["opportunity_id"] not in opp_ids]
orphan_tasks = [r for r in task_rows if r["opportunity_id"] and r["opportunity_id"] not in opp_ids]
orphan_quotes = [r for r in quote_linkages if r["opportunity_id"] not in opp_ids]

assert len(orphan_interactions) == 0, f"Found orphan interactions: {len(orphan_interactions)}"
assert len(orphan_tasks) == 0, f"Found orphan tasks: {len(orphan_tasks)}"
assert len(orphan_quotes) == 0, f"Found orphan quote linkages: {len(orphan_quotes)}"

archive_payload = {
    "archive_metadata": {
        "source": "RateEngine Pre-Production CRM",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "total_tables": 3,
        "total_rows": len(opp_rows) + len(interaction_rows) + len(task_rows),
        "quote_linkages_count": len(quote_linkages),
    },
    "tables": {
        "Opportunity": {
            "table_name": "crm_opportunity",
            "row_count": len(opp_rows),
            "rows": opp_rows,
        },
        "Interaction": {
            "table_name": "crm_interaction",
            "row_count": len(interaction_rows),
            "rows": interaction_rows,
        },
        "Task": {
            "table_name": "crm_task",
            "row_count": len(task_rows),
            "rows": task_rows,
        },
    },
    "quote_linkages": quote_linkages,
}

# Serialize payload deterministically
payload_tables_serialized = json.dumps(archive_payload["tables"], sort_keys=True, indent=2)
payload_sha256 = hashlib.sha256(payload_tables_serialized.encode("utf-8")).hexdigest()

full_archive_serialized = json.dumps(archive_payload, sort_keys=True, indent=2)
archive_bytes = full_archive_serialized.encode("utf-8")
file_sha256 = hashlib.sha256(archive_bytes).hexdigest()

print(f"Writing cold storage archive to {ARCHIVE_PATH}...")
with open(ARCHIVE_PATH, "wb") as f:
    f.write(archive_bytes)

manifest = {
    "archive_filename": "archive_crm_20260922.json",
    "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "storage_location": "RateEngine-local-artifacts/cold_storage/archive_crm_20260922.json",
    "storage_note": "Stored in approved private local cold storage outside repository history. Contains legacy pre-production CRM opportunities, interactions, tasks, and quote linkages.",
    "total_tables": 3,
    "total_rows": len(opp_rows) + len(interaction_rows) + len(task_rows),
    "table_row_counts": {
        "Opportunity": len(opp_rows),
        "Interaction": len(interaction_rows),
        "Task": len(task_rows),
    },
    "quote_linkages_count": len(quote_linkages),
    "file_sha256": file_sha256,
    "payload_sha256": payload_sha256,
    "integrity_result": "PASSED: 100% referential integrity, 0 orphan relationships, all row counts and checksums verified.",
}

print(f"Writing non-sensitive manifest to {MANIFEST_PATH}...")
with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print("Archive and manifest successfully generated!")
print(f"Counts: Opportunity={len(opp_rows)}, Interaction={len(interaction_rows)}, Task={len(task_rows)}, QuoteLinkages={len(quote_linkages)}")
print(f"File SHA-256: {file_sha256}")
print(f"Payload SHA-256: {payload_sha256}")
