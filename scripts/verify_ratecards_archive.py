"""
Verify integrity of legacy Ratecard archive manifest and optional cold-storage archive.
"""
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_COLD_STORAGE = Path("C:/Users/commercial.manager/dev/RateEngine-local-artifacts/cold_storage/archive_ratecards_20260923.json")


def verify_manifest(manifest_path: Path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_counts = {
        "PartnerRateCard": 7,
        "PartnerRateLane": 32,
        "PartnerRate": 434,
    }

    assert manifest["total_tables"] == 3, f"Expected 3 tables, got {manifest['total_tables']}"
    assert manifest["total_rows"] == 473, f"Expected 473 rows, got {manifest['total_rows']}"
    assert manifest["table_row_counts"] == expected_counts, "Table row counts mismatch against expected"
    assert manifest["file_sha256"] == "3d3e24aeb14be37e5181a4681f2061d2f962f7798a9c44cf49b5aad1a59ed143"
    assert manifest["payload_sha256"] == "6e14dbdd84bf60d6103981517704c7a87632164cefd0b7006d4fa28b17866e35"
    assert "storage_location" in manifest
    assert "credentials" not in json.dumps(manifest).lower()

    print(f"Manifest {manifest_path} verified successfully.")
    print(f"3 tables, 473 rows (7 cards, 32 lanes, 434 rates), SHA256: {manifest['payload_sha256']}")
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
    card_ids = {r["id"] for r in tables["PartnerRateCard"]["rows"]}
    lane_ids = {r["id"] for r in tables["PartnerRateLane"]["rows"]}

    for r in tables["PartnerRateLane"]["rows"]:
        assert r["rate_card_id"] in card_ids, f"Orphan lane {r['id']} missing card {r['rate_card_id']}"

    for r in tables["PartnerRate"]["rows"]:
        assert r["lane_id"] in lane_ids, f"Orphan rate {r['id']} missing lane {r['lane_id']}"

    print(f"Cold-storage archive {archive_path} verified against manifest.")
    print(f"File SHA-256: {file_sha} (MATCH)")
    print(f"Payload SHA-256: {payload_sha256} (MATCH)")
    return True


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    manifest_file = repo_root / "docs" / "archive" / "archive_ratecards_20260923_manifest.json"
    manifest_data = verify_manifest(manifest_file)

    archive_target = None
    if len(sys.argv) > 1:
        archive_target = Path(sys.argv[1])
    elif DEFAULT_COLD_STORAGE.exists():
        archive_target = DEFAULT_COLD_STORAGE

    if archive_target and archive_target.exists():
        verify_cold_archive(archive_target, manifest_data)
