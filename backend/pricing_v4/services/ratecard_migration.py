"""
Legacy Ratecard Migration Service for Wave 2C1.

Audits, classifies, and evaluates legacy V3 ratecards (PartnerRateCard,
PartnerRateLane, PartnerRate) against the clean Phase 3 Rate Matrix
(RateSheet -> RateLine -> RateApplicability -> RateTier).

Enforces commercial invariants:
- BUY vs SELL separation
- approved SELL without re-margining
- source currency preservation
- strict validity window
- basis and tier integrity
- fails closed on ambiguous mappings, missing ProductCodes, or partial card migrations
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.geo_models import GeoLocation, GeoLocationIdentifier
from django.db import transaction
from django.utils import timezone
from parties.party_models import PartyMaster, PartyRole
from ratecards.models import (
    PartnerRate,
    PartnerRateCard,
    PartnerRateLane,
)

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)


class RatecardClassification:
    MIGRATE = "MIGRATE"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"
    INVALID_OR_TEST = "INVALID_OR_TEST"
    INVESTIGATE = "INVESTIGATE"


@dataclass
class RateEvaluationResult:
    rate_id: int
    card_id: int
    card_name: str
    lane_id: int
    component_code: str
    rate_type: str
    currency_code: str
    classification: str
    is_usable: bool
    status: str  # 'matched', 'blocked', 'archive-only', 'invalid'
    blocker_reasons: list[str] = field(default_factory=list)
    mapped_product_code: str | None = None
    target_line_id: str | None = None


@dataclass
class MigrationAuditReport:
    total_cards: int = 0
    total_lanes: int = 0
    total_rates: int = 0
    classification_counts: dict[str, int] = field(default_factory=lambda: {
        RatecardClassification.MIGRATE: 0,
        RatecardClassification.ARCHIVE_ONLY: 0,
        RatecardClassification.INVALID_OR_TEST: 0,
        RatecardClassification.INVESTIGATE: 0,
    })
    parity_counts: dict[str, int] = field(default_factory=lambda: {
        "matched": 0,
        "blocked": 0,
        "archive-only": 0,
        "invalid": 0,
    })
    target_rows_created: dict[str, int] = field(default_factory=lambda: {
        "RateSheet": 0,
        "RateLine": 0,
        "RateApplicability": 0,
        "RateTier": 0,
    })
    card_summaries: list[dict[str, Any]] = field(default_factory=list)
    rate_evaluations: list[RateEvaluationResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


class RatecardMigrationService:
    """Service to audit, classify, and migrate legacy ratecards."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    def audit_and_classify(self) -> MigrationAuditReport:
        """Run complete audit and classification across all legacy ratecard rows."""
        report = MigrationAuditReport()
        cards = PartnerRateCard.objects.all().order_by("id")
        report.total_cards = cards.count()
        report.total_lanes = PartnerRateLane.objects.count()
        report.total_rates = PartnerRate.objects.count()

        for card in cards:
            card_summary = self._evaluate_card(card)
            report.card_summaries.append(card_summary)
            for rate_res in card_summary["rate_results"]:
                report.rate_evaluations.append(rate_res)
                report.classification_counts[rate_res.classification] += 1
                report.parity_counts[rate_res.status] += 1
                if rate_res.blocker_reasons:
                    for reason in rate_res.blocker_reasons:
                        blocker_entry = f"Card {card.id} ({card.name}) / Rate {rate_res.rate_id} [{rate_res.component_code}]: {reason}"
                        if blocker_entry not in report.blockers:
                            report.blockers.append(blocker_entry)

        return report

    def _evaluate_card(self, card: PartnerRateCard) -> dict[str, Any]:
        """Classify and evaluate an individual ratecard and its child rates."""
        lanes = card.lanes.all()
        rates = PartnerRate.objects.filter(lane__rate_card=card).select_related(
            "lane", "service_component", "lane__origin_airport", "lane__destination_airport"
        )

        card_blockers = []
        is_card_invalid = False
        is_card_investigate = False
        is_card_archive_only = False

        # 1. Check Card-Level Validity & Classification
        if "(Test)" in card.name or "test" in card.name.lower():
            is_card_invalid = True
            card_blockers.append("Card is explicitly marked as Test / Prototype data.")

        # Card 16 check: PX Export Buy Rates with corrupted supplier
        if "PX Export Buy Rates" in card.name and card.supplier and "Real World" in card.supplier.name:
            is_card_invalid = True
            card_blockers.append(
                "Counterparty mismatch: Air Niugini (PX) buy card assigned to vendor 'Real World Logistics'."
            )

        # Card 15 check: Name says Sell Rates but DB rate_type is BUY_RATE, valid_from is null
        if "Sell Rates" in card.name and card.rate_type == "BUY_RATE":
            is_card_investigate = True
            card_blockers.append(
                "Commercial identity conflict: Card name specifies 'Sell Rates' but database rate_type is 'BUY_RATE'."
            )

        if not card.valid_from:
            is_card_investigate = True
            card_blockers.append(
                "Missing mandatory validity: valid_from is NULL (violates clean RateSheet schema constraint)."
            )

        # Check for AUD destination charges on import cards (Cards 10 & 11)
        if card.currency_code == "AUD":
            dest_comps = rates.filter(
                service_component__code__in=[
                    "DOC_IMP", "AGENCY_IMP", "HANDLING", "TERM_INT", "CARTAGE", "PICKUP_FUEL_DST"
                ]
            )
            if dest_comps.exists():
                is_card_archive_only = True
                card_blockers.append(
                    "Commercial invariant violation: Destination import charges denominated in AUD instead of PNG local PGK."
                )

        # Check for service level mismatches
        if card.service_level not in ["STANDARD", "EXPRESS", "DEFERRED"]:
            card_blockers.append(
                f"Non-standard service_level '{card.service_level}' (RateApplicability supports EXPRESS, STANDARD, DEFERRED)."
            )

        # Check for unmapped service components across the card
        unmapped_components = set()
        for r in rates:
            comp_code = r.service_component.code
            pc_code = self._resolve_commercial_product_code(comp_code, r.lane.direction)
            if not pc_code:
                unmapped_components.add(comp_code)

        if unmapped_components:
            is_card_archive_only = True
            card_blockers.append(
                f"Unmapped service components lacking canonical CommercialProductCode: {sorted(unmapped_components)}."
            )

        # Check for partial/conflicting fee definitions on Card 14
        if card.rate_type == "SELL_RATE" and rates.count() > 100:
            is_card_archive_only = True
            card_blockers.append(
                "Overlapping duplicate fee variants on export sell card; superseded by clean V4 ExportSellRate tariffs."
            )

        # Determine Card Primary Classification
        if is_card_invalid:
            classification = RatecardClassification.INVALID_OR_TEST
            status = "invalid"
        elif is_card_investigate:
            classification = RatecardClassification.INVESTIGATE
            status = "blocked"
        elif is_card_archive_only:
            classification = RatecardClassification.ARCHIVE_ONLY
            status = "archive-only"
        else:
            classification = RatecardClassification.MIGRATE
            status = "matched"

        rate_results = []
        for r in rates:
            rate_blockers = list(card_blockers)
            pc_code = self._resolve_commercial_product_code(
                r.service_component.code, r.lane.direction
            )

            if not pc_code:
                rate_blockers.append(
                    f"No unambiguous CommercialProductCode found for legacy component '{r.service_component.code}'."
                )

            # Check fuel basis mismatch
            if "FUEL" in r.service_component.code and r.unit in ["SHIPMENT", "PER_SHIPMENT"]:
                rate_blockers.append(
                    f"Fuel surcharge '{r.service_component.code}' defined as flat shipment fee ({r.rate_per_shipment_fcy}) instead of percentage basis."
                )

            # Fail closed on ambiguous/partial migration
            rate_usable = (len(rate_blockers) == 0) and (classification == RatecardClassification.MIGRATE)
            rate_status = status
            if classification == RatecardClassification.ARCHIVE_ONLY:
                rate_status = "archive-only" if not is_card_invalid else "invalid"
                # If specific rate has blockers, ensure marked
                if not rate_usable and rate_status not in ["invalid", "archive-only"]:
                    rate_status = "blocked"
            elif classification == RatecardClassification.INVESTIGATE:
                rate_status = "blocked"
            elif classification == RatecardClassification.INVALID_OR_TEST:
                rate_status = "invalid"

            rate_results.append(
                RateEvaluationResult(
                    rate_id=r.id,
                    card_id=card.id,
                    card_name=card.name,
                    lane_id=r.lane.id,
                    component_code=r.service_component.code,
                    rate_type=card.rate_type,
                    currency_code=card.currency_code,
                    classification=classification,
                    is_usable=rate_usable,
                    status=rate_status,
                    blocker_reasons=rate_blockers,
                    mapped_product_code=pc_code,
                )
            )

        return {
            "card_id": card.id,
            "card_name": card.name,
            "rate_type": card.rate_type,
            "currency_code": card.currency_code,
            "lanes_count": lanes.count(),
            "rates_count": rates.count(),
            "classification": classification,
            "blockers": card_blockers,
            "rate_results": rate_results,
        }

    def _resolve_commercial_product_code(
        self, comp_code: str, direction: str
    ) -> str | None:
        """Resolve a legacy ServiceComponent code to a canonical ProductCode string."""
        # Clean direction prefix
        dir_prefix = "EXP" if direction == "EXPORT" else "IMP"

        # Direct canonical mappings
        if comp_code in ["FRT_AIR", "FRT_AIR_EXP", "AIR_FREIGHT"]:
            return f"{dir_prefix}-FRT-AIR"
        if comp_code == "PICKUP":
            return f"{dir_prefix}-PICKUP"
        if comp_code in ["AWB_FEE", "DOC_EXP_AWB"] and direction == "EXPORT":
            return "EXP-AWB"
        if comp_code in ["DOC_EXP", "DOC_EXP_BIC"] and direction == "EXPORT":
            return "EXP-DOC"
        if comp_code in ["HND_EXP_BSC", "TERM_EXP_SELL"] and direction == "EXPORT":
            return "EXP-TERM"
        if comp_code in ["HND_EXP_BPC", "BUILD_UP"] and direction == "EXPORT":
            return "EXP-BUILDUP"
        if comp_code in ["SEC_EXP_MXC", "SECURITY_SELL"] and direction == "EXPORT":
            return "EXP-SCREEN"
        if comp_code in ["CLEAR_EXP", "CLEARANCE_SELL"] and direction == "EXPORT":
            return "EXP-CLEAR"
        if comp_code in ["AGENCY_EXP", "AGENCY_EXP_SELL"] and direction == "EXPORT":
            return "EXP-AGENCY"
        if comp_code in ["HND_EXP_RAC", "DG_ACCEPTANCE"] and direction == "EXPORT":
            return "EXP-DG"
        if comp_code in ["HND_EXP_VA", "VALUABLE_HANDLING"] and direction == "EXPORT":
            return "EXP-VCH"
        if comp_code in ["DOC_EXP_LCC", "LIVESTOCK_DOC"] and direction == "EXPORT":
            return "EXP-LPC"

        # Import specific
        if comp_code == "DOC_EXP" and direction == "IMPORT":
            return "IMP-DOC-ORIGIN"
        if comp_code == "AGENCY_EXP" and direction == "IMPORT":
            return "IMP-AGENCY-ORIGIN"
        if comp_code == "AWB_FEE" and direction == "IMPORT":
            return "IMP-AWB-ORIGIN"
        if comp_code == "CTO" and direction == "IMPORT":
            return "IMP-CTO-ORIGIN"
        if comp_code == "XRAY" and direction == "IMPORT":
            return "IMP-SCREEN-ORIGIN"

        # Unresolved
        return None

    @transaction.atomic
    def execute_migration(self, card_ids: list[int] | None = None) -> MigrationAuditReport:
        """
        Execute migration into clean Rate Matrix (RateSheet -> RateLine -> RateApplicability -> RateTier).
        Fails closed on any ambiguous or partial card.
        """
        report = self.audit_and_classify()

        cards = PartnerRateCard.objects.all()
        if card_ids:
            cards = cards.filter(id__in=card_ids)

        for card in cards:
            card_eval = next((c for c in report.card_summaries if c["card_id"] == card.id), None)
            if not card_eval:
                continue

            # Strict gate: Only migrate cards classified as MIGRATE with 100% usable rates
            if card_eval["classification"] != RatecardClassification.MIGRATE:
                continue

            all_rates_usable = all(r.is_usable for r in card_eval["rate_results"])
            if not all_rates_usable:
                continue

            if not self.dry_run:
                self._persist_clean_rate_matrix(card, card_eval, report)

        return report

    def _persist_clean_rate_matrix(
        self,
        legacy_card: PartnerRateCard,
        card_eval: dict[str, Any],
        report: MigrationAuditReport,
    ):
        """Persist clean RateSheet, RateLine, RateApplicability, RateTier idempotently."""
        # 1. Resolve or create PartyMaster counterparty
        carrier_party = None
        customer_party = None

        if legacy_card.rate_type == "BUY_RATE" and legacy_card.supplier:
            # Map supplier to PartyMaster
            supplier_name = legacy_card.supplier.name
            country_code = "PG"
            if "AU" in supplier_name:
                country_code = "AU"
            carrier_party, _ = PartyMaster.objects.get_or_create(
                legal_name=supplier_name,
                country_code=country_code,
                defaults={"entity_type": "CARRIER", "is_active": True},
            )
            PartyRole.objects.get_or_create(
                party=carrier_party,
                role_type=PartyRole.RoleType.CARRIER,
                defaults={"is_active": True},
            )

        # 2. Idempotent RateSheet creation
        rate_type_clean = "BUY" if legacy_card.rate_type == "BUY_RATE" else "SELL"
        sheet, created_sheet = RateSheet.objects.get_or_create(
            name=f"Migrated: {legacy_card.name}",
            defaults={
                "rate_type": rate_type_clean,
                "transport_mode": RateSheet.TransportMode.AIR,
                "currency_code": legacy_card.currency_code,
                "valid_from": legacy_card.valid_from or timezone.now().date(),
                "valid_until": legacy_card.valid_until,
                "carrier": carrier_party,
                "party": customer_party,
                "is_active": True,
                "version": 1,
            },
        )
        if created_sheet:
            report.target_rows_created["RateSheet"] += 1

        # 3. Process lanes and rates
        for r_res in card_eval["rate_results"]:
            if not r_res.is_usable:
                continue

            legacy_rate = PartnerRate.objects.get(id=r_res.rate_id)
            legacy_lane = legacy_rate.lane

            # Resolve CommercialProductCode
            cpc = CommercialProductCode.objects.filter(code=r_res.mapped_product_code).first()
            if not cpc:
                continue

            # Determine rate basis
            if legacy_rate.tiering_json and legacy_rate.tiering_json.get("breaks"):
                rate_basis = RateLine.RateBasis.TIERED_WEIGHT
                unit_rate = None
            elif legacy_rate.unit in ["KG", "PER_KG"]:
                rate_basis = RateLine.RateBasis.PER_KG
                unit_rate = legacy_rate.rate_per_kg_fcy
            else:
                rate_basis = RateLine.RateBasis.FLAT
                unit_rate = legacy_rate.rate_per_shipment_fcy

            # Idempotent RateLine
            rate_line, created_line = RateLine.objects.get_or_create(
                sheet=sheet,
                product_code=cpc,
                rate_basis=rate_basis,
                defaults={
                    "unit_rate": unit_rate,
                    "min_charge": legacy_rate.min_charge_fcy,
                    "max_charge": legacy_rate.max_charge_fcy,
                },
            )
            if created_line:
                report.target_rows_created["RateLine"] += 1
                r_res.target_line_id = str(rate_line.id)

            # Resolve GeoLocations
            origin_geo = None
            dest_geo = None
            if legacy_lane.origin_airport:
                origin_geo = self._resolve_or_create_airport_geo(legacy_lane.origin_airport)
            if legacy_lane.destination_airport:
                dest_geo = self._resolve_or_create_airport_geo(legacy_lane.destination_airport)

            # RateApplicability (1:1 with RateLine)
            clean_direction = legacy_lane.direction if legacy_lane.direction in ["IMPORT", "EXPORT", "DOMESTIC"] else ""
            clean_service_level = (
                legacy_card.service_level
                if legacy_card.service_level in ["EXPRESS", "STANDARD", "DEFERRED"]
                else RateApplicability.ServiceLevel.STANDARD
            )

            _app, created_app = RateApplicability.objects.get_or_create(
                rate_line=rate_line,
                defaults={
                    "origin": origin_geo,
                    "destination": dest_geo,
                    "direction": clean_direction,
                    "service_level": clean_service_level,
                },
            )
            if created_app:
                report.target_rows_created["RateApplicability"] += 1

            # RateTiers for TIERED_WEIGHT
            if rate_basis == RateLine.RateBasis.TIERED_WEIGHT and legacy_rate.tiering_json:
                breaks = legacy_rate.tiering_json.get("breaks", [])
                for i, b in enumerate(breaks):
                    min_q = Decimal(str(b["min_kg"]))
                    max_q = (
                        Decimal(str(breaks[i + 1]["min_kg"]))
                        if i + 1 < len(breaks)
                        else None
                    )
                    tier_rate = Decimal(str(b["rate_per_kg"]))

                    _tier, created_tier = RateTier.objects.get_or_create(
                        rate_line=rate_line,
                        min_quantity=min_q,
                        defaults={
                            "max_quantity": max_q,
                            "unit_rate": tier_rate,
                        },
                    )
                    if created_tier:
                        report.target_rows_created["RateTier"] += 1

    def _resolve_or_create_airport_geo(self, airport) -> GeoLocation:
        """Resolve or create a normalized GeoLocation for an airport."""
        iata = airport.iata_code.strip().upper()
        # Look for existing identifier
        ident = GeoLocationIdentifier.objects.filter(
            scheme=GeoLocationIdentifier.Scheme.IATA, code=iata
        ).first()
        if ident:
            return ident.location

        # Create GeoLocation
        country_code = (
            airport.city.country.code
            if airport.city and airport.city.country
            else ("PG" if iata == "POM" else "AU")
        )
        location = GeoLocation.objects.create(
            canonical_name=airport.name or f"{iata} Airport",
            country_code=country_code,
            location_type=GeoLocation.LocationType.AIRPORT,
            is_active=True,
        )
        GeoLocationIdentifier.objects.create(
            location=location,
            scheme=GeoLocationIdentifier.Scheme.IATA,
            code=iata,
        )
        return location
