import csv
import json
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from quotes.management.commands.spot_productcode_masterdata_audit import (
    build_masterdata_audit,
    CATEGORY_EXISTING_PRODUCT_CODE,
    CATEGORY_ALIAS_REQUIRED,
    CATEGORY_NEW_PRODUCT_CODE,
    CATEGORY_MANUAL_REVIEW,
)
from quotes.management.commands.spot_productcode_remediation_plan import (
    _group_for,
    _confidence,
    _reason,
    _recommended_product_code,
    APPLY_APPROVED_REQUEST,
    APPLY_EXISTING_PRODUCT_CODE,
    CREATE_ALIAS_MAPPING,
    CREATE_NEW_PRODUCT_CODE,
    MANUAL_REVIEW,
)


class Command(BaseCommand):
    help = "Generate a decision table for human review of remaining unresolved SPOT charge labels."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["csv", "json"],
            default="csv",
            help="Output format. Default is csv.",
        )
        parser.add_argument(
            "--output",
            required=True,
            help="Path to write the output decision table file.",
        )

    def handle(self, *args, **options):
        output_path = options["output"]
        format_type = options["format"]

        # Run masterdata diagnostics
        audit = build_masterdata_audit()
        
        rows = []
        for item in audit.get("labels", []):
            group = _group_for(item)
            pc = _recommended_product_code(group, item)
            confidence = _confidence(group, item)

            # Determine existing matches
            existing = []
            for am in item.get("active_alias_matches", []):
                p_code = am.get("product_code", {})
                existing.append(f"{p_code.get('code')} - {p_code.get('description')} (ID: {p_code.get('id')})")
            for am in item.get("existing_approved_product_code_request_matches", []):
                if am.get("approved_product_code_id"):
                    existing.append(f"Approved Request (ID: {am.get('approved_product_code_id')})")
            existing_matches_str = "; ".join(existing)

            # Determine fuzzy matches
            fuzzy = []
            for match in item.get("existing_product_code_matches", []):
                match_str = f"{match.get('code')} - {match.get('description')} (ID: {match.get('id')})"
                if match_str not in existing:
                    fuzzy.append(match_str)
            fuzzy_matches_str = "; ".join(fuzzy)

            # Requires human approval: any low/medium confidence or new/manual action
            requires_human_approval = "true" if (confidence != "HIGH" or group in {CREATE_NEW_PRODUCT_CODE, MANUAL_REVIEW}) else "false"

            decision_notes = _reason(group, item)
            if requires_human_approval == "true":
                decision_notes += " Requires explicit human review and approval before mapping is finalized."

            rows.append({
                "normalized_label": item["normalized_label"],
                "display_labels_seen": "; ".join(f"{v['label']} ({v['count']})" for v in item["source_label_variants"]),
                "occurrence_count": item["occurrence_count"],
                "current_category": item["remediation_category"],
                "current_action": item["recommended_action"],
                "existing_matches": existing_matches_str,
                "fuzzy_matches": fuzzy_matches_str,
                "recommended_action": group,
                "recommended_product_code_id": pc["id"] if pc else "",
                "recommended_product_code_code": pc["code"] if pc else "",
                "recommended_product_code_description": pc["description"] if pc else "",
                "confidence": confidence,
                "requires_human_approval": requires_human_approval,
                "decision_notes": decision_notes,
            })

        if format_type == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2, sort_keys=True)
        else:
            fieldnames = [
                "normalized_label",
                "display_labels_seen",
                "occurrence_count",
                "current_category",
                "current_action",
                "existing_matches",
                "fuzzy_matches",
                "recommended_action",
                "recommended_product_code_id",
                "recommended_product_code_code",
                "recommended_product_code_description",
                "confidence",
                "requires_human_approval",
                "decision_notes",
            ]
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        self.stdout.write(f"Successfully generated decision table: {output_path}")
