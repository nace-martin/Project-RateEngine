import csv
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from quotes.management.commands.spot_productcode_masterdata_audit import (
    CATEGORY_ALIAS_REQUIRED,
    CATEGORY_EXISTING_PRODUCT_CODE,
    CATEGORY_MANUAL_REVIEW,
    CATEGORY_NEW_PRODUCT_CODE,
    build_masterdata_audit,
    normalize_label,
    _line_queryset,
)


APPLY_EXISTING_PRODUCT_CODE = "APPLY_EXISTING_PRODUCT_CODE"
CREATE_ALIAS_MAPPING = "CREATE_ALIAS_MAPPING"
CREATE_NEW_PRODUCT_CODE = "CREATE_NEW_PRODUCT_CODE"
MANUAL_REVIEW = "MANUAL_REVIEW"
APPLY_APPROVED_REQUEST = "APPLY_APPROVED_REQUEST"

GROUPS = [
    APPLY_EXISTING_PRODUCT_CODE,
    CREATE_ALIAS_MAPPING,
    CREATE_NEW_PRODUCT_CODE,
    MANUAL_REVIEW,
    APPLY_APPROVED_REQUEST,
]


def _affected_context() -> dict:
    grouped = defaultdict(lambda: {"charge_line_ids": [], "envelope_ids": set()})
    for line in _line_queryset():
        normalized = normalize_label(line.normalized_label or line.source_label or line.description)
        if not normalized:
            continue
        grouped[normalized]["charge_line_ids"].append(str(line.id))
        grouped[normalized]["envelope_ids"].add(str(line.envelope_id))
    return grouped


def _recommended_product_code(group: str, item: dict) -> dict | None:
    if group in {CREATE_NEW_PRODUCT_CODE, MANUAL_REVIEW}:
        return None
    approved = item["existing_approved_product_code_request_matches"]
    if approved and approved[0].get("approved_product_code_id"):
        pc_id = approved[0]["approved_product_code_id"]
        for match in item["existing_product_code_matches"]:
            if match["id"] == pc_id:
                return match
        return {"id": pc_id, "code": "", "description": ""}
    aliases = item["active_alias_matches"]
    if aliases:
        return aliases[0]["product_code"]
    matches = item["existing_product_code_matches"]
    return matches[0] if matches else None


def _group_for(item: dict) -> str:
    approved = item["existing_approved_product_code_request_matches"]
    if approved and approved[0].get("approved_product_code_id"):
        return APPLY_APPROVED_REQUEST
    category = item["remediation_category"]
    if category == CATEGORY_EXISTING_PRODUCT_CODE:
        return APPLY_EXISTING_PRODUCT_CODE
    if category == CATEGORY_ALIAS_REQUIRED:
        return CREATE_ALIAS_MAPPING
    if category == CATEGORY_NEW_PRODUCT_CODE:
        return CREATE_NEW_PRODUCT_CODE
    if category == CATEGORY_MANUAL_REVIEW:
        return MANUAL_REVIEW
    return MANUAL_REVIEW


def _confidence(group: str, item: dict) -> str:
    if group == APPLY_APPROVED_REQUEST:
        return "HIGH"
    if group == APPLY_EXISTING_PRODUCT_CODE and item["active_alias_matches"]:
        return "HIGH"
    if group == CREATE_ALIAS_MAPPING and item["existing_product_code_matches"]:
        return "MEDIUM"
    if group == CREATE_NEW_PRODUCT_CODE and item["pending_product_code_request_matches"]:
        return "MEDIUM"
    return "LOW" if group == MANUAL_REVIEW else "MEDIUM"


def _reason(group: str, item: dict) -> str:
    if group == APPLY_APPROVED_REQUEST:
        return "Approved ProductCode request exists; charge lines still need explicit manual application."
    if group == APPLY_EXISTING_PRODUCT_CODE:
        return "Existing alias or ProductCode match is available for this unresolved label."
    if group == CREATE_ALIAS_MAPPING:
        return "Catalogue or canonical hint exists, but this source label still needs an explicit alias decision."
    if group == CREATE_NEW_PRODUCT_CODE:
        return "No safe existing ProductCode mapping was found for a repeated or requested unresolved label."
    return "Label is too broad or source-specific for a bulk mapping recommendation."


def build_remediation_plan() -> dict:
    audit = build_masterdata_audit()
    affected = _affected_context()
    plan = {group: [] for group in GROUPS}
    counts = Counter()

    for item in audit["labels"]:
        group = _group_for(item)
        pc = _recommended_product_code(group, item)
        ctx = affected[item["normalized_label"]]
        row = {
            "normalized_label": item["normalized_label"],
            "display_source_labels_seen": item["source_label_variants"],
            "occurrence_count": item["occurrence_count"],
            "affected_charge_line_ids": ctx["charge_line_ids"],
            "affected_envelope_ids": sorted(ctx["envelope_ids"]),
            "existing_product_code_match": item["existing_product_code_matches"][0] if item["existing_product_code_matches"] else None,
            "approved_request_match": item["existing_approved_product_code_request_matches"][0] if item["existing_approved_product_code_request_matches"] else None,
            "recommended_product_code_id": pc["id"] if pc else None,
            "recommended_product_code_code": pc["code"] if pc else "",
            "recommended_product_code_description": pc["description"] if pc else "",
            "confidence": _confidence(group, item),
            "reason": _reason(group, item),
            "action_required": group,
        }
        plan[group].append(row)
        counts[group] += 1

    return {
        "readiness_status": audit["readiness_status"],
        "summary": {
            "unique_unresolved_labels": audit["readiness_summary"]["unique_unresolved_labels"],
            "unresolved_charge_lines": audit["readiness_summary"]["unresolved_charge_lines"],
            "action_group_counts": {group: counts[group] for group in GROUPS},
            "writes_performed": False,
        },
        "plan": plan,
    }


def _csv_rows(report: dict):
    for group in GROUPS:
        for item in report["plan"][group]:
            yield {
                "action_required": group,
                "normalized_label": item["normalized_label"],
                "source_labels_seen": "; ".join(f"{v['label']} ({v['count']})" for v in item["display_source_labels_seen"]),
                "occurrence_count": item["occurrence_count"],
                "affected_charge_line_ids": ";".join(item["affected_charge_line_ids"]),
                "affected_envelope_ids": ";".join(item["affected_envelope_ids"]),
                "recommended_product_code_id": item["recommended_product_code_id"] or "",
                "recommended_product_code_code": item["recommended_product_code_code"],
                "recommended_product_code_description": item["recommended_product_code_description"],
                "confidence": item["confidence"],
                "reason": item["reason"],
            }


class Command(BaseCommand):
    help = "Read-only SPOT ProductCode remediation plan export."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["json", "csv"], default="json")
        parser.add_argument("--output", help="Required for CSV output.")

    def handle(self, *args, **options):
        report = build_remediation_plan()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        output = options.get("output")
        if not output:
            raise CommandError("--output is required when --format csv")

        fieldnames = [
            "action_required",
            "normalized_label",
            "source_labels_seen",
            "occurrence_count",
            "affected_charge_line_ids",
            "affected_envelope_ids",
            "recommended_product_code_id",
            "recommended_product_code_code",
            "recommended_product_code_description",
            "confidence",
            "reason",
        ]
        with open(output, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(_csv_rows(report))
        self.stdout.write(f"Wrote read-only remediation plan to {output}")
