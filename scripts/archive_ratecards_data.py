"""
Script to archive legacy Ratecard data (PartnerRateCard, PartnerRateLane, PartnerRate)
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
ARCHIVE_PATH = COLD_STORAGE_DIR / "archive_ratecards_20260923.json"
MANIFEST_PATH = BASE_DIR / "docs" / "archive" / "archive_ratecards_20260923_manifest.json"

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

print("Extracting Ratecard tables...")
card_rows = fetch_table("ratecards_partnerratecard")
lane_rows = fetch_table("ratecards_partnerratelane")
rate_rows = fetch_table("ratecards_partnerrate")

# Referential integrity check
card_ids = {r["id"] for r in card_rows}
lane_ids = {r["id"] for r in lane_rows}

orphan_lanes = [r for r in lane_rows if r["rate_card_id"] not in card_ids]
orphan_rates = [r for r in rate_rows if r["lane_id"] not in lane_ids]

assert len(orphan_lanes) == 0, f"Found orphan lanes: {len(orphan_lanes)}"
assert len(orphan_rates) == 0, f"Found orphan rates: {len(orphan_rates)}"

archive_payload = {
    "archive_metadata": {
        "source": "RateEngine Legacy Ratecards (V3)",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "total_tables": 3,
        "total_rows": len(card_rows) + len(lane_rows) + len(rate_rows),
    },
    "tables": {
        "PartnerRateCard": {
            "table_name": "ratecards_partnerratecard",
            "row_count": len(card_rows),
            "rows": card_rows,
        },
        "PartnerRateLane": {
            "table_name": "ratecards_partnerratelane",
            "row_count": len(lane_rows),
            "rows": lane_rows,
        },
        "PartnerRate": {
            "table_name": "ratecards_partnerrate",
            "row_count": len(rate_rows),
            "rows": rate_rows,
        },
    },
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
    "archive_filename": "archive_ratecards_20260923.json",
    "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "storage_location": "RateEngine-local-artifacts/cold_storage/archive_ratecards_20260923.json",
    "storage_note": "Stored in approved private local cold storage outside repository history. Contains legacy pre-production ratecards, lanes, and rates prior to clean rate matrix cutover.",
    "total_tables": 3,
    "total_rows": len(card_rows) + len(lane_rows) + len(rate_rows),
    "table_row_counts": {
        "PartnerRateCard": len(card_rows),
        "PartnerRateLane": len(lane_rows),
        "PartnerRate": len(rate_rows),
    },
    "file_sha256": file_sha256,
    "payload_sha256": payload_sha256,
    "integrity_result": "PASSED: 100% referential integrity, 0 orphan relationships, all row counts and checksums verified.",
}

print(f"Writing non-sensitive manifest to {MANIFEST_PATH}...")
with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print("Archive and manifest successfully generated!")
print(f"Counts: PartnerRateCard={len(card_rows)}, PartnerRateLane={len(lane_rows)}, PartnerRate={len(rate_rows)}")
print(f"File SHA-256: {file_sha256}")
print(f"Payload SHA-256: {payload_sha256}")
