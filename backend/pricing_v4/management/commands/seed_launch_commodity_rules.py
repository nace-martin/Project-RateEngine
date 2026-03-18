from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_date

from pricing_v4.models import CommodityChargeRule, ProductCode


@dataclass(frozen=True)
class MarkerProductCodeDef:
    id: int
    code: str
    description: str
    domain: str
    category: str
    gst_treatment: str
    revenue_code: str
    cost_code: str


MARKER_PRODUCT_CODES = [
    MarkerProductCodeDef(1091, "EXP-PER-SPECIAL", "Export Perishable Routing Marker", "EXPORT", "HANDLING", "ZERO_RATED", "4490", "5490"),
    MarkerProductCodeDef(2091, "IMP-DG-SPECIAL", "Import Dangerous Goods Handling", "IMPORT", "HANDLING", "STANDARD", "4490", "5490"),
    MarkerProductCodeDef(2092, "IMP-AVI-SPECIAL", "Import Live Animal Handling", "IMPORT", "HANDLING", "STANDARD", "4490", "5490"),
    MarkerProductCodeDef(2093, "IMP-HVC-SPECIAL", "Import High Value Handling", "IMPORT", "HANDLING", "STANDARD", "4490", "5490"),
    MarkerProductCodeDef(2094, "IMP-PER-SPECIAL", "Import Perishable Routing Marker", "IMPORT", "HANDLING", "STANDARD", "4490", "5490"),
    MarkerProductCodeDef(3091, "DOM-DG-SPECIAL", "Domestic DG Routing Marker", "DOMESTIC", "HANDLING", "STANDARD", "4490", "5490"),
    MarkerProductCodeDef(3092, "DOM-PER-SPECIAL", "Domestic Perishable Routing Marker", "DOMESTIC", "HANDLING", "STANDARD", "4490", "5490"),
]


def _rule(
    *,
    shipment_type: str,
    service_scope: str,
    commodity_code: str,
    product_code: str,
    leg: str,
    trigger_mode: str,
    notes: str,
    payment_term: Optional[str] = None,
) -> dict:
    return {
        "shipment_type": shipment_type,
        "service_scope": service_scope,
        "commodity_code": commodity_code,
        "product_code": product_code,
        "leg": leg,
        "trigger_mode": trigger_mode,
        "payment_term": payment_term,
        "notes": notes,
    }


LAUNCH_RULES = [
    # Export: only DG has a seeded commercial product with real coverage today.
    _rule(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="DG",
        product_code="EXP-DG",
        leg="ORIGIN",
        trigger_mode="AUTO",
        notes="Launch export DG handling. Uses seeded EXP-DG when coverage exists.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2D",
        commodity_code="DG",
        product_code="EXP-DG",
        leg="ORIGIN",
        trigger_mode="AUTO",
        notes="Launch export DG handling. Uses seeded EXP-DG when coverage exists.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="AVI",
        product_code="EXP-LPC",
        leg="ORIGIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Live animal export pricing remains manual until origin COGS and airline rules are stable.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2D",
        commodity_code="AVI",
        product_code="EXP-LPC",
        leg="ORIGIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Live animal export pricing remains manual until origin COGS and airline rules are stable.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="HVC",
        product_code="EXP-VCH",
        leg="ORIGIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="High-value export handling requires manual commercial confirmation at launch.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2D",
        commodity_code="HVC",
        product_code="EXP-VCH",
        leg="ORIGIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="High-value export handling requires manual commercial confirmation at launch.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="PER",
        product_code="EXP-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Perishable export rates remain airline/handling dependent at launch.",
    ),
    _rule(
        shipment_type="EXPORT",
        service_scope="D2D",
        commodity_code="PER",
        product_code="EXP-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Perishable export rates remain airline/handling dependent at launch.",
    ),
    # Import: route all launch special commodities away from standard compute for now.
    _rule(
        shipment_type="IMPORT",
        service_scope="A2D",
        commodity_code="DG",
        product_code="IMP-DG-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import DG uses standard quote when destination-local DG tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="D2D",
        commodity_code="DG",
        product_code="IMP-DG-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import DG uses standard quote when destination-local DG tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="A2D",
        commodity_code="AVI",
        product_code="IMP-AVI-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import AVI uses standard quote when destination-local live-animal tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="D2D",
        commodity_code="AVI",
        product_code="IMP-AVI-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import AVI uses standard quote when destination-local live-animal tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="A2D",
        commodity_code="HVC",
        product_code="IMP-HVC-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import HVC uses standard quote when destination-local high-value tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="D2D",
        commodity_code="HVC",
        product_code="IMP-HVC-SPECIAL",
        leg="DESTINATION",
        trigger_mode="AUTO",
        notes="Import HVC uses standard quote when destination-local high-value tariffs exist; otherwise it falls back on missing commodity coverage.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="A2D",
        commodity_code="PER",
        product_code="IMP-PER-SPECIAL",
        leg="DESTINATION",
        trigger_mode="REQUIRES_SPOT",
        notes="Import perishable charges remain partner-driven at launch.",
    ),
    _rule(
        shipment_type="IMPORT",
        service_scope="D2D",
        commodity_code="PER",
        product_code="IMP-PER-SPECIAL",
        leg="DESTINATION",
        trigger_mode="REQUIRES_SPOT",
        notes="Import perishable charges remain partner-driven at launch.",
    ),
    # Domestic: use existing markers where possible, otherwise route with explicit markers.
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2A",
        commodity_code="AVI",
        product_code="DOM-LIVE-ANIMAL",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic live animal pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2D",
        commodity_code="AVI",
        product_code="DOM-LIVE-ANIMAL",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic live animal pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2A",
        commodity_code="AVI",
        product_code="DOM-LIVE-ANIMAL",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic live animal pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2D",
        commodity_code="AVI",
        product_code="DOM-LIVE-ANIMAL",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic live animal pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2A",
        commodity_code="HVC",
        product_code="DOM-VALUABLE",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic valuable cargo pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2D",
        commodity_code="HVC",
        product_code="DOM-VALUABLE",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic valuable cargo pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2A",
        commodity_code="HVC",
        product_code="DOM-VALUABLE",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic valuable cargo pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2D",
        commodity_code="HVC",
        product_code="DOM-VALUABLE",
        leg="MAIN",
        trigger_mode="REQUIRES_MANUAL",
        notes="Domestic valuable cargo pricing remains manual at launch.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2A",
        commodity_code="DG",
        product_code="DOM-DG-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic DG remains SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2D",
        commodity_code="DG",
        product_code="DOM-DG-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic DG remains SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2A",
        commodity_code="DG",
        product_code="DOM-DG-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic DG remains SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2D",
        commodity_code="DG",
        product_code="DOM-DG-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic DG remains SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2A",
        commodity_code="PER",
        product_code="DOM-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic perishables remain SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="A2D",
        commodity_code="PER",
        product_code="DOM-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic perishables remain SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2A",
        commodity_code="PER",
        product_code="DOM-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic perishables remain SPOT-only until explicit product/rate coverage exists.",
    ),
    _rule(
        shipment_type="DOMESTIC",
        service_scope="D2D",
        commodity_code="PER",
        product_code="DOM-PER-SPECIAL",
        leg="MAIN",
        trigger_mode="REQUIRES_SPOT",
        notes="Domestic perishables remain SPOT-only until explicit product/rate coverage exists.",
    ),
]


class Command(BaseCommand):
    help = "Seed a conservative launch commodity rule matrix for standard-vs-SPOT routing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--effective-from",
            default=str(date.today()),
            help="Effective-from date for seeded rules in YYYY-MM-DD format (default: today).",
        )
        parser.add_argument(
            "--effective-to",
            default="",
            help="Optional effective-to date in YYYY-MM-DD format.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be seeded without writing changes.",
        )

    def handle(self, *args, **options):
        effective_from = self._parse_required_date(options["effective_from"], "--effective-from")
        effective_to = self._parse_optional_date(options["effective_to"], "--effective-to")
        dry_run = options["dry_run"]

        if effective_to and effective_to < effective_from:
            raise ValueError("--effective-to must be on or after --effective-from")

        self.stdout.write("=" * 72)
        self.stdout.write("Seeding launch commodity routing matrix")
        self.stdout.write("=" * 72)
        self.stdout.write(f"Effective from: {effective_from}")
        self.stdout.write(f"Effective to:   {effective_to or 'open-ended'}")
        self.stdout.write(f"Mode:           {'DRY RUN' if dry_run else 'APPLY'}")

        with transaction.atomic():
            product_summary = self._seed_marker_product_codes(dry_run=dry_run)
            rule_summary = self._seed_rules(
                effective_from=effective_from,
                effective_to=effective_to,
                dry_run=dry_run,
            )
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Commodity launch matrix ready."))
        self.stdout.write(
            f"Marker product codes: created={product_summary['created']} updated={product_summary['updated']} reused={product_summary['reused']}"
        )
        self.stdout.write(
            f"Commodity rules: created={rule_summary['created']} updated={rule_summary['updated']}"
        )
        self.stdout.write("")
        self.stdout.write("Rule coverage summary:")
        for key, count in sorted(rule_summary["by_group"].items()):
            self.stdout.write(f"  {key}: {count}")
        self.stdout.write("")
        self.stdout.write("Notes:")
        self.stdout.write("  - Export DG is seeded as AUTO, but standard DG compute is still blocked elsewhere until DG quoting is enabled.")
        self.stdout.write("  - AVI/HVC/PER default to REQUIRES_MANUAL or REQUIRES_SPOT where stable commercial coverage is not yet seeded.")

    def _seed_marker_product_codes(self, *, dry_run: bool) -> dict:
        summary = {"created": 0, "updated": 0, "reused": 0}
        for marker in MARKER_PRODUCT_CODES:
            defaults = {
                "description": marker.description,
                "domain": marker.domain,
                "category": marker.category,
                "is_gst_applicable": marker.gst_treatment == ProductCode.GST_TREATMENT_STANDARD,
                "gst_rate": "0.10" if marker.gst_treatment == ProductCode.GST_TREATMENT_STANDARD else "0.00",
                "gst_treatment": marker.gst_treatment,
                "gl_revenue_code": marker.revenue_code,
                "gl_cost_code": marker.cost_code,
                "default_unit": ProductCode.UNIT_SHIPMENT,
                "percent_of_product_code": None,
            }
            product = ProductCode.objects.filter(code=marker.code).first()
            if product:
                changed = False
                for field, value in defaults.items():
                    if getattr(product, field) != value:
                        setattr(product, field, value)
                        changed = True
                if changed:
                    product.save()
                    summary["updated"] += 1
                    action = "Would update" if dry_run else "Updated"
                else:
                    summary["reused"] += 1
                    action = "Would reuse" if dry_run else "Reused"
            else:
                product = ProductCode(id=marker.id, code=marker.code, **defaults)
                product.full_clean()
                product.save()
                summary["created"] += 1
                action = "Would create" if dry_run else "Created"

            self.stdout.write(f"  {action} ProductCode {marker.code}")
        return summary

    def _seed_rules(
        self,
        *,
        effective_from: date,
        effective_to: Optional[date],
        dry_run: bool,
    ) -> dict:
        summary = {"created": 0, "updated": 0, "by_group": {}}
        for rule_data in LAUNCH_RULES:
            product = ProductCode.objects.get(code=rule_data["product_code"])
            lookup = {
                "shipment_type": rule_data["shipment_type"],
                "service_scope": rule_data["service_scope"],
                "commodity_code": rule_data["commodity_code"],
                "product_code": product,
                "leg": rule_data["leg"],
                "origin_code": None,
                "destination_code": None,
                "payment_term": rule_data["payment_term"],
            }
            defaults = {
                "trigger_mode": rule_data["trigger_mode"],
                "is_active": True,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "notes": rule_data["notes"],
            }
            existing = CommodityChargeRule.objects.filter(**lookup).first()
            if existing:
                changed = False
                for field, value in defaults.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if changed:
                    existing.full_clean()
                    existing.save()
                    summary["updated"] += 1
                    action = "Would update" if dry_run else "Updated"
                else:
                    action = "Would reuse" if dry_run else "Reused"
            else:
                new_rule = CommodityChargeRule(**lookup, **defaults)
                new_rule.full_clean()
                new_rule.save()
                summary["created"] += 1
                action = "Would create" if dry_run else "Created"

            group_key = (
                f"{rule_data['shipment_type']}:{rule_data['commodity_code']}:"
                f"{rule_data['trigger_mode']}"
            )
            summary["by_group"][group_key] = summary["by_group"].get(group_key, 0) + 1
            self.stdout.write(
                f"  {action} rule {rule_data['shipment_type']} {rule_data['service_scope']} "
                f"{rule_data['commodity_code']} -> {rule_data['product_code']} ({rule_data['trigger_mode']})"
            )
        return summary

    @staticmethod
    def _parse_required_date(raw_value: str, flag_name: str) -> date:
        parsed = parse_date(str(raw_value or "").strip())
        if not parsed:
            raise ValueError(f"{flag_name} must be a valid date in YYYY-MM-DD format")
        return parsed

    @staticmethod
    def _parse_optional_date(raw_value: str, flag_name: str) -> Optional[date]:
        raw_value = str(raw_value or "").strip()
        if not raw_value:
            return None
        parsed = parse_date(raw_value)
        if not parsed:
            raise ValueError(f"{flag_name} must be a valid date in YYYY-MM-DD format")
        return parsed
