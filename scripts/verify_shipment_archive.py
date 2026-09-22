"""
Verify integrity of legacy shipments archive manifest and optional cold-storage archive.
"""
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_COLD_STORAGE = Path("C:/Users/commercial.manager/dev/RateEngine-local-artifacts/cold_storage/archive_connotes_20260922.json")


def verify_manifest(manifest_path: Path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_counts = {
        "ShipmentSettings": 1,
        "ShipmentAddressBookEntry": 3,
        "ShipmentTemplate": 0,
        "Shipment": 4,
        "ShipmentPiece": 4,
        "ShipmentCharge": 4,
        "ShipmentDocument": 2,
        "ShipmentEvent": 14,
    }

    assert manifest["total_tables"] == 8, f"Expected 8 tables, got {manifest['total_tables']}"
    assert manifest["total_rows"] == 32, f"Expected 32 rows, got {manifest['total_rows']}"
    assert manifest["table_row_counts"] == expected_counts, "Table row counts mismatch against expected"
    assert manifest["file_sha256"] == "9a0f74067559bffbb00a46d321bd3d0715defe9061846cb1f9b63c75baec68b6"
    assert manifest["payload_sha256"] == "0ced2c3fe9a342a96f0f3e7fb6503b8d908d46dacd0f38357abd4bebd8dec039"
    assert "storage_location" in manifest
    assert "credentials" not in json.dumps(manifest).lower()

    print(f"Manifest {manifest_path} verified successfully.")
    print(f"8 tables, 32 rows, SHA256: {manifest['payload_sha256']}")
    print(f"Cold storage target: {manifest['storage_location']}")
    return manifest


def verify_cold_archive(archive_path: Path, manifest: dict):
    with open(archive_path, "rb") as f:
        content = f.read()
    file_sha = hashlib.sha256(content).hexdigest()
    assert file_sha == manifest["file_sha256"], f"File hash mismatch: {file_sha} vs {manifest['file_sha256']}"

    data = json.loads(content.decode("utf-8"))
    tables = data.get("tables", {})
    payload_serialized = json.dumps(tables, sort_keys=True, indent=2)
    payload_sha256 = hashlib.sha256(payload_serialized.encode("utf-8")).hexdigest()
    assert payload_sha256 == manifest["payload_sha256"], f"Payload hash mismatch: {payload_sha256} vs {manifest['payload_sha256']}"

    # Verify FK relationships
    shipment_ids = {r["id"] for r in tables["Shipment"]["rows"]}
    for child in ["ShipmentPiece", "ShipmentCharge", "ShipmentDocument", "ShipmentEvent"]:
        for r in tables[child]["rows"]:
            assert r["shipment"] in shipment_ids, f"Orphan child row {r['id']} in {child}"

    print(f"Cold-storage archive {archive_path} verified against manifest.")
    print(f"File SHA-256: {file_sha} (MATCH)")
    print(f"Payload SHA-256: {payload_sha256} (MATCH)")
    return True


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    manifest_file = repo_root / "docs" / "archive" / "archive_connotes_20260922_manifest.json"
    manifest_data = verify_manifest(manifest_file)

    archive_target = None
    if len(sys.argv) > 1:
        archive_target = Path(sys.argv[1])
    elif DEFAULT_COLD_STORAGE.exists():
        archive_target = DEFAULT_COLD_STORAGE

    if archive_target and archive_target.exists():
        verify_cold_archive(archive_target, manifest_data)
