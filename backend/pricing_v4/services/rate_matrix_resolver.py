"""Read-only Rate Matrix resolver (Pilot Gate B3J).

Resolves one stored tariff line for one fully stated context and returns its
native facts. It is deterministic and fail-closed, and it is not used by any
quote, engine, adapter, or dispatcher: legacy pricing remains authoritative.

Outcomes (clean-database-architecture-v2.1.md section 3.5.1) are exactly:

``EXACT_MATCH``      one active line matches; its native facts are returned.
``NO_MATCH``         nothing matches. Missing coverage is never filled in.
``AMBIGUOUS``        more than one line could match. No precedence is applied.
``INVALID_CONTEXT``  the context cannot be resolved as stated.

Rules: active sheets only; validity end dates inclusive; a blank applicability
value means ANY; no specific-over-general precedence; BUY requires a supplier and
native currency never chooses between competing costs; SELL must match the
requested quote currency; no FX; no reverse-direction inference; no fallback to
another route or currency. A tier's lower bound is inclusive and its upper bound
exclusive, and a matched tier prices the whole weight. A legitimate zero rate is
a match, not a missing rate.

The resolver only reads. It never writes, converts, or computes a charge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q

from core.geo_models import GeoLocationIdentifier
from pricing_v4.rate_matrix_models import RateApplicability, RateLine, RateSheet

EXACT_MATCH = "EXACT_MATCH"
NO_MATCH = "NO_MATCH"
AMBIGUOUS = "AMBIGUOUS"
INVALID_CONTEXT = "INVALID_CONTEXT"

BUY = RateSheet.RateType.BUY.value
SELL = RateSheet.RateType.SELL.value
RATE_TYPES = (BUY, SELL)
DIRECTIONS = tuple(RateApplicability.Direction.values)
PAYMENT_TERMS = ("",) + tuple(RateApplicability.PaymentTerm.values)
SERVICE_LEVELS = ("",) + tuple(RateApplicability.ServiceLevel.values)
PILOT_TRANSPORT_MODE = RateSheet.TransportMode.AIR.value


@dataclass(frozen=True)
class ResolutionContext:
    """Everything a resolution depends on. Nothing is defaulted from elsewhere."""

    rate_type: str
    direction: str
    effective_date: date
    product_code: str
    origin_iata: str | None = None
    destination_iata: str | None = None
    payment_term: str = ""
    quote_currency: str | None = None
    supplier_id: uuid.UUID | None = None
    service_level: str = ""
    commodity_category: str = ""
    equipment_type: str = ""
    chargeable_weight: Decimal | None = None
    transport_mode: str = PILOT_TRANSPORT_MODE
    # Structural comparison only: return a tiered line without selecting a tier.
    allow_line_without_weight: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "rate_type": self.rate_type, "transport_mode": self.transport_mode, "direction": self.direction,
            "effective_date": self.effective_date.isoformat() if isinstance(self.effective_date, date) else None,
            "product_code": self.product_code, "origin_iata": self.origin_iata,
            "destination_iata": self.destination_iata, "payment_term": self.payment_term,
            "quote_currency": self.quote_currency,
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
            "service_level": self.service_level, "commodity_category": self.commodity_category,
            "equipment_type": self.equipment_type,
            "chargeable_weight": str(self.chargeable_weight) if self.chargeable_weight is not None else None,
        }


@dataclass(frozen=True)
class Tier:
    min_quantity: Decimal
    max_quantity: Decimal | None
    unit_rate: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_quantity": str(self.min_quantity),
            "max_quantity": None if self.max_quantity is None else str(self.max_quantity),
            "unit_rate": str(self.unit_rate),
        }


@dataclass(frozen=True)
class ResolvedTariff:
    """Native facts of one stored line and its provenance. No amount is calculated."""

    line_id: uuid.UUID
    sheet_id: uuid.UUID
    sheet_name: str
    sheet_version: int
    source_reference: str
    rate_type: str
    transport_mode: str
    currency_code: str
    valid_from: date
    valid_until: date | None
    supplier_id: uuid.UUID | None
    supplier_name: str | None
    product_code: str
    rate_basis: str
    unit_rate: Decimal | None
    additive_flat_amount: Decimal | None
    min_charge: Decimal | None
    max_charge: Decimal | None
    percentage_rate: Decimal | None
    percentage_basis_product_code: str | None
    tiers: tuple[Tier, ...]
    selected_tier: Tier | None
    direction: str
    origin_iata: str | None
    destination_iata: str | None
    payment_term: str
    service_level: str
    commodity_category: str
    equipment_type: str

    def as_dict(self) -> dict[str, Any]:
        def amount(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "line_id": str(self.line_id), "sheet_id": str(self.sheet_id), "sheet_name": self.sheet_name,
            "sheet_version": self.sheet_version, "source_reference": self.source_reference,
            "rate_type": self.rate_type, "transport_mode": self.transport_mode,
            "currency_code": self.currency_code, "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
            "supplier_name": self.supplier_name, "product_code": self.product_code,
            "rate_basis": self.rate_basis, "unit_rate": amount(self.unit_rate),
            "additive_flat_amount": amount(self.additive_flat_amount), "min_charge": amount(self.min_charge),
            "max_charge": amount(self.max_charge), "percentage_rate": amount(self.percentage_rate),
            "percentage_basis_product_code": self.percentage_basis_product_code,
            "tiers": [tier.as_dict() for tier in self.tiers],
            "selected_tier": self.selected_tier.as_dict() if self.selected_tier else None,
            "applicability": {
                "direction": self.direction, "origin_iata": self.origin_iata,
                "destination_iata": self.destination_iata, "payment_term": self.payment_term,
                "service_level": self.service_level, "commodity_category": self.commodity_category,
                "equipment_type": self.equipment_type,
            },
        }


@dataclass(frozen=True)
class Resolution:
    outcome: str
    context: ResolutionContext
    tariff: ResolvedTariff | None = None
    candidates: tuple[ResolvedTariff, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return self.outcome == EXACT_MATCH

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome, "context": self.context.as_dict(), "reasons": list(self.reasons),
            "tariff": self.tariff.as_dict() if self.tariff else None,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


def resolve(context: ResolutionContext, *, using: str = "default") -> Resolution:
    """Resolve one tariff line. Only SELECT statements are issued."""
    problems = _context_problems(context)
    if problems:
        return Resolution(INVALID_CONTEXT, context, reasons=tuple(problems))

    geo: dict[str, uuid.UUID] = {}
    for iata in (context.origin_iata, context.destination_iata):
        if iata is None:
            continue
        found = list(
            GeoLocationIdentifier.objects.using(using)
            .filter(scheme=GeoLocationIdentifier.Scheme.IATA, code=iata)
            .select_related("location").order_by("id")[:2]
        )
        if len(found) != 1 or not found[0].location.is_active:
            reason = "is not unique" if len(found) > 1 else "does not resolve to an active location"
            return Resolution(INVALID_CONTEXT, context, reasons=(f"IATA '{iata}' {reason}.",))
        geo[iata] = found[0].location_id

    origin_id = geo.get(context.origin_iata) if context.origin_iata else None
    destination_id = geo.get(context.destination_iata) if context.destination_iata else None
    candidates = list(_candidate_lines(context, origin_id, destination_id, using))
    if not candidates:
        return Resolution(NO_MATCH, context, reasons=("No active line matches the stated context.",))

    tariffs = tuple(_tariff(line) for line in candidates)
    if len(candidates) > 1:
        return Resolution(
            AMBIGUOUS, context, candidates=tariffs,
            reasons=(
                (
                    f"{len(candidates)} active lines could match this context; no precedence is applied "
                    "and nothing is chosen."
                ),
            ),
        )

    line = candidates[0]
    if line.rate_basis == RateLine.RateBasis.TIERED_WEIGHT:
        if context.chargeable_weight is None:
            if not context.allow_line_without_weight:
                return Resolution(
                    INVALID_CONTEXT, context, candidates=tariffs,
                    reasons=("chargeable_weight is required to resolve a tiered rate.",),
                )
            return Resolution(EXACT_MATCH, context, tariff=tariffs[0])
        selected = [
            tier for tier in tariffs[0].tiers
            if tier.min_quantity <= context.chargeable_weight
            and (tier.max_quantity is None or context.chargeable_weight < tier.max_quantity)
        ]
        if not selected:
            return Resolution(
                NO_MATCH, context, candidates=tariffs,
                reasons=(f"No tier covers chargeable weight {context.chargeable_weight}; it is not priced.",),
            )
        if len(selected) > 1:
            return Resolution(
                AMBIGUOUS, context, candidates=tariffs,
                reasons=(f"{len(selected)} tiers cover chargeable weight {context.chargeable_weight}.",),
            )
        return Resolution(EXACT_MATCH, context, tariff=_with_tier(tariffs[0], selected[0]))
    return Resolution(EXACT_MATCH, context, tariff=tariffs[0])


# ----------------------------------------------------------------------------- internals


def _context_problems(context: ResolutionContext) -> list[str]:
    problems = []
    if context.rate_type not in RATE_TYPES:
        problems.append(f"rate_type must be one of {', '.join(RATE_TYPES)}.")
    if context.transport_mode != PILOT_TRANSPORT_MODE:
        problems.append(f"transport_mode must be {PILOT_TRANSPORT_MODE} for the Pilot.")
    if context.direction not in DIRECTIONS:
        problems.append(f"direction must be one of {', '.join(DIRECTIONS)}.")
    if not isinstance(context.effective_date, date):
        problems.append("effective_date must be a date.")
    if not context.product_code or context.product_code != context.product_code.strip():
        problems.append("product_code is required.")
    if context.payment_term not in PAYMENT_TERMS:
        problems.append("payment_term must be PREPAID, COLLECT, or blank.")
    if context.service_level not in SERVICE_LEVELS:
        problems.append("service_level must be EXPRESS, STANDARD, DEFERRED, or blank.")
    if context.rate_type == BUY and context.supplier_id is None:
        problems.append("A BUY resolution requires a supplier.")
    if context.rate_type == SELL:
        if not context.quote_currency:
            problems.append("A SELL resolution requires the requested quote currency.")
        if context.supplier_id is not None:
            problems.append("A SELL resolution must not name a supplier.")
    for name in ("origin_iata", "destination_iata"):
        value = getattr(context, name)
        if value is not None and not (len(value) == 3 and value.isalpha() and value.isupper()):
            problems.append(f"{name} must be null or a three-letter upper-case IATA code.")
    if context.chargeable_weight is not None and context.chargeable_weight < 0:
        problems.append("chargeable_weight must not be negative.")
    return problems


def _candidate_lines(context: ResolutionContext, origin_id, destination_id, using: str):
    sheets = Q(
        sheet__is_active=True, sheet__rate_type=context.rate_type,
        sheet__transport_mode=context.transport_mode, sheet__valid_from__lte=context.effective_date,
    ) & (Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=context.effective_date))
    if context.rate_type == BUY:
        # BUY currency is deliberately not filtered: it cannot choose between competing costs.
        sheets &= Q(sheet__carrier_id=context.supplier_id)
    else:
        sheets &= Q(sheet__currency_code=context.quote_currency) & Q(sheet__carrier__isnull=True)

    def geo(field_name: str, location_id) -> Q:
        blank = Q(**{f"applicability__{field_name}__isnull": True})
        return blank if location_id is None else blank | Q(**{f"applicability__{field_name}_id": location_id})

    applicability = (
        Q(applicability__direction__in=[context.direction, ""])
        & geo("origin", origin_id) & geo("destination", destination_id)
        & Q(applicability__payment_term__in=[context.payment_term, ""])
        & Q(applicability__service_level__in=[context.service_level, ""])
        & Q(applicability__commodity_category__in=[context.commodity_category, ""])
        & Q(applicability__equipment_type__in=[context.equipment_type, ""])
    )
    return (
        RateLine.objects.using(using)
        .filter(sheets, applicability, product_code__code=context.product_code)
        .select_related(
            "sheet", "sheet__carrier", "product_code", "percentage_basis_product_code",
            "applicability", "applicability__origin", "applicability__destination",
        )
        .prefetch_related("tiers", "applicability__origin__identifiers", "applicability__destination__identifiers")
        .order_by("sheet__name", "sheet__version", "id")
    )


def _iata(location) -> str | None:
    if location is None:
        return None
    codes = sorted(
        identifier.code for identifier in location.identifiers.all()
        if identifier.scheme == GeoLocationIdentifier.Scheme.IATA
    )
    return codes[0] if len(codes) == 1 else None


def _tariff(line: RateLine) -> ResolvedTariff:
    sheet, applicability = line.sheet, line.applicability
    tiers = tuple(
        Tier(tier.min_quantity, tier.max_quantity, tier.unit_rate)
        for tier in sorted(line.tiers.all(), key=lambda tier: tier.min_quantity)
    )
    return ResolvedTariff(
        line_id=line.id, sheet_id=sheet.id, sheet_name=sheet.name, sheet_version=sheet.version,
        source_reference=sheet.source_reference, rate_type=sheet.rate_type, transport_mode=sheet.transport_mode,
        currency_code=sheet.currency_code, valid_from=sheet.valid_from, valid_until=sheet.valid_until,
        supplier_id=sheet.carrier_id, supplier_name=sheet.carrier.legal_name if sheet.carrier else None,
        product_code=line.product_code.code, rate_basis=line.rate_basis, unit_rate=line.unit_rate,
        additive_flat_amount=line.additive_flat_amount, min_charge=line.min_charge, max_charge=line.max_charge,
        percentage_rate=line.percentage_rate,
        percentage_basis_product_code=(
            line.percentage_basis_product_code.code if line.percentage_basis_product_code else None
        ),
        tiers=tiers, selected_tier=None, direction=applicability.direction,
        origin_iata=_iata(applicability.origin), destination_iata=_iata(applicability.destination),
        payment_term=applicability.payment_term, service_level=applicability.service_level,
        commodity_category=applicability.commodity_category, equipment_type=applicability.equipment_type,
    )


def _with_tier(tariff: ResolvedTariff, tier: Tier) -> ResolvedTariff:
    return replace(tariff, selected_tier=tier)
