import csv
import json
import os
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB
from quotes.management.commands.spot_productcode_masterdata_audit import normalize_label
from quotes.management.commands.spot_productcode_close_loop_report import build_report as build_close_loop_report

CREATE_ALIAS_MAPPING = "CREATE_ALIAS_MAPPING"
CREATE_NEW_PRODUCT_CODE = "CREATE_NEW_PRODUCT_CODE"
APPLY_EXISTING_PRODUCT_CODE = "APPLY_EXISTING_PRODUCT_CODE"
LEAVE_FOR_MANUAL_REVIEW = "LEAVE_FOR_MANUAL_REVIEW"

VALID_ACTIONS = {
    CREATE_ALIAS_MAPPING,
    CREATE_NEW_PRODUCT_CODE,
    APPLY_EXISTING_PRODUCT_CODE,
    LEAVE_FOR_MANUAL_REVIEW,
}


def robust_normalize(value: str | None) -> str:
    if not value:
        return ""
    # Standardize en-dash and em-dash to standard hyphen
    val = str(value).replace("–", "-").replace("—", "-")
    # Collapse whitespace and lowercase
    return " ".join(val.split()).lower()


class Command(BaseCommand):
    help = "Applies human-approved SPOT ProductCode decision table mappings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            required=True,
            help="Path to the reviewed CSV decision table.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually apply changes to the database. Default is dry-run.",
        )
        parser.add_argument(
            "--format",
            choices=["json", "text"],
            default="text",
            help="Output format (json or text). Default is text.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv"]
        dry_run = not options["apply"]
        output_format = options["format"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV file does not exist: {csv_path}")

        # Get system user/reconciliation user
        User = get_user_model()
        system_user = (
            User.objects.filter(username="system").first()
            or User.objects.filter(is_superuser=True).first()
            or User.objects.first()
        )

        try:
            close_loop_report = build_close_loop_report()
            readiness_before = close_loop_report["readiness_status"]
            unresolved_count_before = close_loop_report["blocking_counts"]["unresolved_product_code_review_lines"]
        except Exception:
            readiness_before = "UNKNOWN"
            unresolved_count_before = 999999

        summary = {
            "dry_run": dry_run,
            "writes_performed": not dry_run,
            "approved_rows_seen": 0,
            "aliases_created": 0,
            "aliases_existing": 0,
            "product_codes_created": 0,
            "charge_lines_resolved": 0,
            "manual_review_deferred": 0,
            "skipped_count": 0,
            "error_count": 0,
            "readiness_before": readiness_before,
            "readiness_after": readiness_before,
            "unique_charge_lines_selected": 0,
            "duplicate_charge_line_matches": 0,
            "charge_line_ids_selected": [],
            "per_row_results": [],
        }

        # Load all unresolved charge lines matching masterdata audit criteria
        unresolved_lines = list(
            SPEChargeLineDB.objects.filter(
                normalization_status__in=[
                    SPEChargeLineDB.NormalizationStatus.UNMAPPED,
                    SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
                ]
            ).exclude(
                manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
                manual_resolved_product_code__isnull=False,
            )
        )

        charge_line_ids_selected = set()
        duplicate_charge_line_matches = 0

        try:
            with transaction.atomic():
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row_idx, row in enumerate(reader, start=2):
                        normalized_label = row.get("normalized_label")
                        approved_action = row.get("approved_action")
                        approved_by_human = (row.get("approved_by_human") or "").strip().lower()
                        confidence = (row.get("confidence") or "").strip().upper()

                        if not normalized_label:
                            summary["skipped_count"] += 1
                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "status": "SKIPPED",
                                "reason": "MISSING_NORMALIZED_LABEL",
                            })
                            continue

                        # Filter for only approved high-confidence rows
                        if approved_by_human != "true" or confidence != "HIGH":
                            summary["skipped_count"] += 1
                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "normalized_label": normalized_label,
                                "status": "SKIPPED",
                                "reason": "UNAPPROVED_OR_LOW_CONFIDENCE",
                            })
                            continue

                        if approved_action not in VALID_ACTIONS:
                            summary["skipped_count"] += 1
                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "normalized_label": normalized_label,
                                "status": "SKIPPED",
                                "reason": f"INVALID_ACTION_{approved_action}",
                            })
                            continue

                        summary["approved_rows_seen"] += 1

                        # Find matching unresolved charge lines robustly by normalized_label ONLY
                        csv_norm = robust_normalize(normalized_label)
                        matching_lines = []
                        for line in unresolved_lines:
                            if robust_normalize(line.normalized_label) == csv_norm:
                                matching_lines.append(line)

                        if approved_action == LEAVE_FOR_MANUAL_REVIEW:
                            summary["manual_review_deferred"] += len(matching_lines)
                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "normalized_label": normalized_label,
                                "action": approved_action,
                                "status": "DEFERRED",
                                "matching_lines_count": len(matching_lines),
                                "notes": row.get("decision_notes"),
                            })
                            continue

                        elif approved_action in (CREATE_ALIAS_MAPPING, APPLY_EXISTING_PRODUCT_CODE):
                            pc_id = row.get("approved_product_code_id")
                            if not pc_id:
                                summary["error_count"] += 1
                                summary["per_row_results"].append({
                                    "row_index": row_idx,
                                    "normalized_label": normalized_label,
                                    "action": approved_action,
                                    "status": "ERROR",
                                    "reason": "MISSING_PRODUCT_CODE_ID",
                                })
                                continue

                            product_code = ProductCode.objects.filter(id=pc_id).first()
                            if not product_code:
                                summary["error_count"] += 1
                                summary["per_row_results"].append({
                                    "row_index": row_idx,
                                    "normalized_label": normalized_label,
                                    "action": approved_action,
                                    "status": "ERROR",
                                    "reason": "PRODUCT_CODE_NOT_FOUND",
                                })
                                continue

                            # Create ChargeAlias if CREATE_ALIAS_MAPPING
                            if approved_action == CREATE_ALIAS_MAPPING:
                                alias_norm = normalize_label(normalized_label)
                                existing_alias = ChargeAlias.objects.filter(
                                    normalized_alias_text=alias_norm,
                                    product_code=product_code,
                                ).first()

                                if existing_alias:
                                    summary["aliases_existing"] += 1
                                else:
                                    if not dry_run:
                                        ChargeAlias.objects.create(
                                            alias_text=normalized_label,
                                            product_code=product_code,
                                            is_active=True,
                                            review_status=ChargeAlias.ReviewStatus.APPROVED,
                                            alias_source=ChargeAlias.AliasSource.ADMIN,
                                        )
                                    summary["aliases_created"] += 1

                            # Resolve charge lines
                            resolved_ids = []
                            for line in matching_lines:
                                line_id_str = str(line.id)
                                if line_id_str in charge_line_ids_selected:
                                    duplicate_charge_line_matches += 1
                                    continue

                                charge_line_ids_selected.add(line_id_str)

                                if not dry_run:
                                    line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                                    line.manual_resolved_product_code = product_code
                                    line.manual_resolution_by = system_user
                                    line.manual_resolution_at = timezone.now()
                                    line.save()
                                resolved_ids.append(line_id_str)

                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "normalized_label": normalized_label,
                                "action": approved_action,
                                "status": "APPLIED" if not dry_run else "WOULD_APPLY",
                                "product_code": product_code.code,
                                "resolved_line_ids": resolved_ids,
                            })

                        elif approved_action == CREATE_NEW_PRODUCT_CODE:
                            new_id = row.get("approved_create_product_code_id")
                            new_code = row.get("approved_create_product_code_code")
                            new_desc = row.get("approved_create_product_code_description")
                            new_domain = row.get("approved_create_product_code_domain")
                            new_category = row.get("approved_create_product_code_category")
                            new_basis = row.get("approved_create_product_code_basis")

                            if not (new_id and new_code and new_desc and new_domain and new_category and new_basis):
                                summary["error_count"] += 1
                                summary["per_row_results"].append({
                                    "row_index": row_idx,
                                    "normalized_label": normalized_label,
                                    "action": approved_action,
                                    "status": "ERROR",
                                    "reason": "MISSING_NEW_PRODUCT_CODE_FIELDS",
                                })
                                continue

                            # Check for duplicates
                            if ProductCode.objects.filter(id=new_id).exists() or ProductCode.objects.filter(code=new_code).exists():
                                summary["error_count"] += 1
                                summary["per_row_results"].append({
                                    "row_index": row_idx,
                                    "normalized_label": normalized_label,
                                    "action": approved_action,
                                    "status": "ERROR",
                                    "reason": "DUPLICATE_PRODUCT_CODE_ID_OR_CODE",
                                })
                                continue

                            # Create ProductCode
                            if not dry_run:
                                product_code = ProductCode.objects.create(
                                    id=new_id,
                                    code=new_code,
                                    description=new_desc,
                                    domain=new_domain,
                                    category=new_category,
                                    default_unit=new_basis,
                                    is_gst_applicable=False,
                                    gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
                                    gst_rate=Decimal("0.1000"),
                                    gl_revenue_code="4000",
                                    gl_cost_code="5000",
                                )
                            else:
                                # Mock for dry-run resolution reporting
                                product_code = ProductCode(id=new_id, code=new_code)

                            summary["product_codes_created"] += 1

                            # Create ChargeAlias
                            alias_norm = normalize_label(normalized_label)
                            existing_alias = ChargeAlias.objects.filter(
                                normalized_alias_text=alias_norm,
                                product_code=product_code,
                            ).first()

                            if existing_alias:
                                summary["aliases_existing"] += 1
                            else:
                                if not dry_run:
                                    ChargeAlias.objects.create(
                                        alias_text=normalized_label,
                                        product_code=product_code,
                                        is_active=True,
                                        review_status=ChargeAlias.ReviewStatus.APPROVED,
                                        alias_source=ChargeAlias.AliasSource.ADMIN,
                                    )
                                summary["aliases_created"] += 1

                            # Resolve charge lines
                            resolved_ids = []
                            for line in matching_lines:
                                line_id_str = str(line.id)
                                if line_id_str in charge_line_ids_selected:
                                    duplicate_charge_line_matches += 1
                                    continue

                                charge_line_ids_selected.add(line_id_str)

                                if not dry_run:
                                    line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                                    line.manual_resolved_product_code = product_code
                                    line.manual_resolution_by = system_user
                                    line.manual_resolution_at = timezone.now()
                                    line.save()
                                resolved_ids.append(line_id_str)

                            summary["per_row_results"].append({
                                "row_index": row_idx,
                                "normalized_label": normalized_label,
                                "action": approved_action,
                                "status": "APPLIED" if not dry_run else "WOULD_APPLY",
                                "product_code": product_code.code,
                                "resolved_line_ids": resolved_ids,
                            })

                # Populate unique metrics
                summary["unique_charge_lines_selected"] = len(charge_line_ids_selected)
                summary["duplicate_charge_line_matches"] = duplicate_charge_line_matches
                summary["charge_line_ids_selected"] = sorted(list(charge_line_ids_selected))
                summary["charge_lines_resolved"] = len(charge_line_ids_selected)

                # Safety check: must not exceed unresolved count before
                if len(charge_line_ids_selected) > unresolved_count_before:
                    summary["error_count"] += 1
                    raise CommandError(
                        f"Safety Check Failed: Total unique charge lines selected ({len(charge_line_ids_selected)}) "
                        f"exceeds unresolved baseline ({unresolved_count_before}). Aborting."
                    )

                if dry_run:
                    raise DryRunRollback()

        except DryRunRollback:
            # Expected dry-run rollback
            pass
        except Exception as e:
            if not isinstance(e, DryRunRollback):
                summary["error_count"] += 1
                summary["per_row_results"].append({
                    "status": "ERROR",
                    "reason": str(e),
                })
            if output_format == "json":
                self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
            else:
                self.stderr.write(f"Error processing CSV: {e}")
            raise e

        # Calculate readiness after
        try:
            readiness_after = build_close_loop_report()["readiness_status"]
            summary["readiness_after"] = readiness_after
        except Exception:
            pass

        if output_format == "json":
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
        else:
            self.stdout.write("=== SPOT ProductCode Decision Apply Output ===")
            self.stdout.write(f"Dry Run: {summary['dry_run']}")
            self.stdout.write(f"Approved Rows Seen: {summary['approved_rows_seen']}")
            self.stdout.write(f"Aliases Created: {summary['aliases_created']}")
            self.stdout.write(f"Aliases Existing: {summary['aliases_existing']}")
            self.stdout.write(f"Product Codes Created: {summary['product_codes_created']}")
            self.stdout.write(f"Unique Charge Lines Selected: {summary['unique_charge_lines_selected']}")
            self.stdout.write(f"Duplicate Charge Line Matches: {summary['duplicate_charge_line_matches']}")
            self.stdout.write(f"Charge Lines Resolved: {summary['charge_lines_resolved']}")
            self.stdout.write(f"Deferred for Manual Review: {summary['manual_review_deferred']}")
            self.stdout.write(f"Skipped Rows: {summary['skipped_count']}")
            self.stdout.write(f"Errors: {summary['error_count']}")
            self.stdout.write(f"Readiness Before: {summary['readiness_before']} -> After: {summary['readiness_after']}")


class DryRunRollback(Exception):
    pass
