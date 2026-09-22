"""
Verify integrity of legacy CRM archive manifest and optional cold-storage archive.
"""
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_COLD_STORAGE = Path("C:/Users/commercial.manager/dev/RateEngine-local-artifacts/cold_storage/archive_crm_20260922.json")


def verify_manifest(manifest_path: Path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_counts = {
        "Opportunity": 88,
        "Interaction": 259,
        "Task": 0,
    }

    assert manifest["total_tables"] == 3, f"Expected 3 tables, got {manifest['total_tables']}"
    assert manifest["total_rows"] == 347, f"Expected 347 rows, got {manifest['total_rows']}"
    assert manifest["quote_linkages_count"] == 60, f"Expected 60 quote linkages, got {manifest['quote_linkages_count']}"
    assert manifest["table_row_counts"] == expected_counts, "Table row counts mismatch against expected"
    assert manifest["file_sha256"] == "6b9c26c0955cb1a32bd01ee075373038974baef80262106800899aa66b9c4891"
    assert manifest["payload_sha256"] == "2fb90f8f0a73e20089a3e0f6816e0eef98eaec879fbeefa3708f27dbfd9d0a13"
    assert "storage_location" in manifest
    assert "credentials" not in json.dumps(manifest).lower()

    print(f"Manifest {manifest_path} verified successfully.")
    print(f"3 tables, 347 rows, 60 quote linkages, SHA256: {manifest['payload_sha256']}")
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
    opp_ids = {r["id"] for r in tables["Opportunity"]["rows"]}
    for child in ["Interaction", "Task"]:
        for r in tables[child]["rows"]:
            if r.get("opportunity_id"):
                assert r["opportunity_id"] in opp_ids, f"Orphan child row {r['id']} in {child}"

    quote_links = data.get("quote_linkages", [])
    for q in quote_links:
        assert q["opportunity_id"] in opp_ids, f"Orphan quote linkage {q['id']}"

    print(f"Cold-storage archive {archive_path} verified against manifest.")
    print(f"File SHA-256: {file_sha} (MATCH)")
    print(f"Payload SHA-256: {payload_sha256} (MATCH)")
    return True


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    manifest_file = repo_root / "docs" / "archive" / "archive_crm_20260922_manifest.json"
    manifest_data = verify_manifest(manifest_file)

    archive_target = None
    if len(sys.argv) > 1:
        archive_target = Path(sys.argv[1])
    elif DEFAULT_COLD_STORAGE.exists():
        archive_target = DEFAULT_COLD_STORAGE

    if archive_target and archive_target.exists():
        verify_cold_archive(archive_target, manifest_data)
