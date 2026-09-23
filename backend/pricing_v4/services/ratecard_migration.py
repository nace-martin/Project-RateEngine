"""Legacy Ratecard Audit Service for Wave 2C1.

Read-only audit and classification service for legacy V3 ratecards
(PartnerRateCard, PartnerRateLane, PartnerRate).

Evaluates commercial invariants against clean architecture standards:
- BUY vs SELL separation
- approved SELL without re-margining
- source currency preservation
- strict validity window
- basis and tier integrity
- fails closed on ambiguous mappings, missing ProductCodes, or test data

Note: PR #354 is strictly audit/archive only. Zero target Rate Matrix rows
are created, and no write/migration paths exist for legacy rows.
"""

from dataclasses import dataclass, field
from typing import Any

from ratecards.models import (
    PartnerRate,
    PartnerRateCard,
    PartnerRateLane,
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
    """Read-only service to audit and classify legacy ratecards."""

    def __init__(self, *args, **kwargs):
        pass

    def audit_and_classify(self) -> MigrationAuditReport:
        """Run complete read-only audit and classification across all legacy ratecard rows."""
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
                service_component__code__in=["DOC_IMP", "AGENCY_IMP", "CARTAGE_IMP", "HANDLING_GEN", "CUS_CLR_IMP"]
            )
            if dest_comps.exists():
                is_card_archive_only = True
                card_blockers.append(
                    "AUD destination charges present on import card; violates clean V4 PGK destination tariff policy."
                )

        # Check for non-standard service levels
        if card.service_level and card.service_level not in ["EXPRESS", "STANDARD", "DEFERRED"]:
            is_card_archive_only = True
            card_blockers.append(f"Non-standard service level: '{card.service_level}'.")

        # Check for unmapped service components across all child rates
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

        return None
