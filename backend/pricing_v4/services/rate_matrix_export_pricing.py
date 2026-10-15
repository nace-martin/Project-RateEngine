"""Rate Matrix export pricing for the Pilot lanes (Pilot Gate B3M-E).

Production integration of the approved Rate Matrix export tariffs behind ONE feature flag. The flag is
OFF by default. With the flag OFF, or for any shipment outside the exact Pilot scope, nothing in this
module is reached and the legacy export engine prices exactly as before.

Selection is made once, up front, by ``select_rate_matrix_export_pricing``. A shipment is either in the
Pilot scope (Rate Matrix mode) or it is not (legacy). **Once Rate Matrix mode is selected there is no
fallback to legacy rates**: every lookup that cannot be resolved exactly raises
``RateMatrixExportPricingError`` and the quote fails closed.

Locked commercial rules (Commercial Manager, 2026-10-12):

- BUY: approved export freight BUY and approved terminal BUY from Rate Matrix sheets; a tier may carry
  its own minimum (``RateTier.min_charge``).
- SELL: approved PGK Rate Matrix SELL. There is no AUD SELL tariff. An explicit SELL receives no margin.
- AUD: ``AUD = (PGK SELL / TT SELL) x (1 + export CAF)`` with TT SELL stored as PGK per AUD, i.e. PGK x
  published BSP TT Sell (BSP calculator: PGK to FCY uses TT Sell). Pure FX is rounded first, then the CAF
  is a separate uplift. The CAF and FX apply only when a conversion actually occurs; a PGK quote needs
  neither. FX is the stored AUD/PGK market fact (policy source priority, maximum age 5 days); missing,
  stale, ambiguous, inverse-only or cross-only FX fails closed.
- GST: CommercialProductCode GST treatment (must agree with the ProductCode the classifier reads) at the
  policy ``gst_standard_percent``.
- Weight: tiered tariffs accept at most four decimal places; the resolver fails closed above that and
  nothing is rounded silently.

This module does not read ExportCOGS, ExportSellRate, LocalCOGSRate, LocalSellRate or Surcharge rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any, Optional

from django.conf import settings

from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_PERCENT_OF_BASE,
    RuleEvaluation,
    evaluate_percent_of_base_rule,
    evaluate_tiered_break_rule,
)
from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.engine.export_engine import ChargeLineResult, ExportPricingEngine, PaymentTerm
from pricing_v4.engine.result_types import QuoteResult, build_tax_breakdown
from pricing_v4.models import ProductCode
from pricing_v4.services import fx_conventions
from pricing_v4.services import rate_matrix_resolver as resolver
from pricing_v4.services.commercial_policy import MissingCommercialPolicyError
from pricing_v4.services.fx_resolver import StaleFxMarketRateError, resolve_market_fx_pair
from quotes.tax_policy import get_png_gst_category

logger = logging.getLogger(__name__)

FLAG_SETTING = "RATE_MATRIX_EXPORT_PRICING_ENABLED"
PILOT_LANES = frozenset({("POM", "BNE"), ("POM", "SYD")})
PILOT_SCOPES = frozenset({"A2A", "D2A"})
PILOT_MODE = "AIR"
PILOT_QUOTE_CURRENCIES = {"PREPAID": "PGK", "COLLECT": "AUD"}
MAX_FX_AGE_DAYS = 5
# Locked export rule: PGK to FCY at the stored TT SELL, then the export CAF as a separate uplift.
CAF_METHOD = fx_conventions.CAF_APPROVED
FX_SIDE_CONVENTION = fx_conventions.FX_APPROVED
PRICING_PATH = "RATE_MATRIX_EXPORT"
LEGACY_PATH = "LEGACY_EXPORT"

_TWO_PLACES = Decimal("0.01")


_USER_MESSAGES = {
    "LANE_NOT_PILOT": "This shipment is outside the approved export pricing scope.",
    "CURRENCY_NOT_PILOT": "This shipment is outside the approved export pricing scope.",
    "SCOPE_NOT_PILOT": "This shipment is outside the approved export pricing scope.",
    "SUPPLIER_NOT_SINGLE": "The approved export supplier tariff could not be determined for this lane.",
    "RESOLVER_AMBIGUOUS": "More than one approved export tariff matches this shipment; pricing was stopped.",
    "SERVICE_COMPONENT_MISSING": (
        "Export pricing configuration is incomplete: a required charge component is not set up."
    ),
    "FX_NOT_DIRECT": "A usable AUD exchange rate is not available; pricing was stopped.",
    "FX_NOT_POSITIVE": "A usable AUD exchange rate is not available; pricing was stopped.",
}
_PRECISION_MESSAGE = (
    "The chargeable weight has more than 4 decimal places and cannot be priced from the approved tariff. "
    "Adjust the piece weights or dimensions."
)
_GENERIC_MESSAGE = "An approved export tariff or classification is incomplete; pricing was stopped."


class RateMatrixExportPricingError(ValueError):
    """Rate Matrix export pricing cannot price this quote. Nothing falls back to legacy rates.

    ``str()`` is the customer-safe text shown by the API; ``code`` and ``message`` carry the technical
    detail (charge codes, sheets) for logs and audit, and are never part of the API response.
    """

    def __init__(self, code: str, message: str):
        if "decimal places" in message:
            user_message = _PRECISION_MESSAGE
        else:
            user_message = _USER_MESSAGES.get(code, _GENERIC_MESSAGE)
        super().__init__(user_message)
        self.code = code
        self.message = message
        logger.warning("Rate Matrix export pricing failed closed: %s: %s", code, message)


# ----------------------------------------------------------------------------- selection


@dataclass(frozen=True)
class Selection:
    """Whether a shipment prices through the Rate Matrix, and why. ``reason`` is always recorded."""

    selected: bool
    reason: str
    flag_enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": PRICING_PATH if self.selected else LEGACY_PATH,
            "flag": FLAG_SETTING, "flag_enabled": self.flag_enabled, "reason": self.reason,
        }


def rate_matrix_export_enabled() -> bool:
    """The feature flag. Only an explicit boolean True enables the path; unset or anything else is OFF."""
    return getattr(settings, FLAG_SETTING, False) is True


def select_rate_matrix_export_pricing(
    *,
    shipment_type: Optional[str],
    mode: Optional[str],
    origin: Optional[str],
    destination: Optional[str],
    service_scope: Optional[str],
    payment_term: Optional[str],
    quote_currency: Optional[str],
    commodity_code: Optional[str],
    is_dangerous_goods: bool,
    spot_envelope_id: Any = None,
    agent_id: Any = None,
    carrier_id: Any = None,
    buy_currency: Optional[str] = None,
    has_overrides: bool = False,
    has_spot_rates: bool = False,
) -> Selection:
    """Exact Pilot lane and scope guard. Evaluated before any pricing; the flag is checked first."""
    enabled = rate_matrix_export_enabled()
    if not enabled:
        return Selection(False, "FLAG_OFF", False)

    def out(reason: str) -> Selection:
        return Selection(False, f"OUT_OF_SCOPE: {reason}", True)

    if str(shipment_type or "").upper() != "EXPORT":
        return out("shipment type is not EXPORT")
    if str(mode or "").upper() != PILOT_MODE:
        return out("transport mode is not AIR")
    lane = (str(origin or "").upper(), str(destination or "").upper())
    if lane not in PILOT_LANES:
        return out(f"lane {lane[0]}-{lane[1]} is not a Pilot lane")
    scope = str(service_scope or "").upper()
    if scope not in PILOT_SCOPES:
        return out(f"service scope '{scope}' is not a Pilot scope")
    term = str(payment_term or "").upper()
    expected_currency = PILOT_QUOTE_CURRENCIES.get(term)
    if expected_currency is None or str(quote_currency or "").upper() != expected_currency:
        return out(f"payment term '{term}' with quote currency '{quote_currency}' is not a Pilot combination")
    if str(commodity_code or DEFAULT_COMMODITY_CODE).upper() != DEFAULT_COMMODITY_CODE:
        return out("commodity is not General Cargo")
    if is_dangerous_goods:
        return out("dangerous goods")
    if spot_envelope_id:
        return out("SPOT pricing is not Rate Matrix priced")
    if agent_id is not None or carrier_id is not None:
        return out("a preferred agent or carrier is not supported by the Rate Matrix path")
    if str(buy_currency or "").upper() not in ("", "PGK"):
        return out("a non-PGK BUY currency is not supported by the Rate Matrix path")
    if has_overrides or has_spot_rates:
        return out("manual overrides or spot rates are present")
    return Selection(True, "IN_SCOPE", True)


# ----------------------------------------------------------------------------- Rate Matrix lookup


class MatrixRate(SimpleNamespace):
    """A Rate Matrix tariff shaped like the legacy rate records the production rate rules evaluate."""


def _legacy_shaped(tariff: resolver.ResolvedTariff) -> MatrixRate:
    rate = MatrixRate(
        currency=tariff.currency_code, rate_type="", amount=None, percent_rate=None, rate_per_kg=None,
        rate_per_shipment=None, min_charge=tariff.min_charge, max_charge=tariff.max_charge, weight_breaks=None,
        is_additive=False, agent=None, tariff=tariff,
    )
    basis = tariff.rate_basis
    if basis == "FLAT":
        rate.rate_type, rate.amount, rate.rate_per_shipment = "FIXED", tariff.unit_rate, tariff.unit_rate
    elif basis == "PER_KG":
        rate.rate_type, rate.amount, rate.rate_per_kg = "PER_KG", tariff.unit_rate, tariff.unit_rate
        if tariff.additive_flat_amount is not None:
            rate.is_additive, rate.rate_per_shipment = True, tariff.additive_flat_amount
    elif basis == "TIERED_WEIGHT":
        rate.weight_breaks = []
        for tier in tariff.tiers:
            entry = {"min_kg": str(tier.min_quantity), "rate": str(tier.unit_rate)}
            if tier.min_charge is not None:
                entry["min_charge"] = str(tier.min_charge)
            rate.weight_breaks.append(entry)
    elif basis == "PERCENTAGE":
        rate.rate_type, rate.amount, rate.percent_rate = "PERCENT", tariff.percentage_rate, tariff.percentage_rate
    else:
        raise RateMatrixExportPricingError(
            "UNSUPPORTED_BASIS", f"Rate basis '{basis}' for {tariff.product_code} is not supported."
        )
    return rate


def _selected_tier_minimum(rate: MatrixRate, weight: Decimal) -> Optional[Decimal]:
    for tier in sorted(rate.weight_breaks or [], key=lambda t: Decimal(str(t["min_kg"])), reverse=True):
        if weight >= Decimal(str(tier["min_kg"])):
            minimum = tier.get("min_charge")
            return None if minimum is None else Decimal(str(minimum))
    return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _text(value: Any) -> Optional[str]:
    return None if value is None else format(Decimal(str(value)).normalize(), "f")


def _tariff_provenance(side: str, tariff: resolver.ResolvedTariff) -> dict[str, Any]:
    return {
        "side": side, "product_code": tariff.product_code, "sheet": tariff.sheet_name,
        "sheet_version": tariff.sheet_version, "sheet_id": str(tariff.sheet_id), "line_id": str(tariff.line_id),
        "source_reference": tariff.source_reference, "supplier": tariff.supplier_name,
        "currency": tariff.currency_code, "rate_basis": tariff.rate_basis,
        "unit_rate": _text(tariff.unit_rate), "additive_flat_amount": _text(tariff.additive_flat_amount),
        "min_charge": _text(tariff.min_charge), "max_charge": _text(tariff.max_charge),
        "percentage_rate": _text(tariff.percentage_rate),
        "percentage_basis_product_code": tariff.percentage_basis_product_code,
        "valid_from": tariff.valid_from.isoformat(),
        "valid_until": tariff.valid_until.isoformat() if tariff.valid_until else None,
        "tiers": [
            {"min": _text(t.min_quantity), "max": _text(t.max_quantity), "rate": _text(t.unit_rate),
             "min_charge": _text(t.min_charge)}
            for t in tariff.tiers
        ],
        "selected_tier_min": _text(tariff.selected_tier.min_quantity) if tariff.selected_tier else None,
    }


# ----------------------------------------------------------------------------- engine


class RateMatrixExportPricingEngine(ExportPricingEngine):
    """The export engine with its tariff authority replaced by the Rate Matrix.

    ``_get_cogs`` / ``_get_sell_rate`` resolve exact Rate Matrix tariffs and never consult a legacy rate
    table. Charge lines are priced in PGK (the native currency of every Pilot tariff) with the production
    rate rules, then converted once per line under the locked AUD rule when the quote currency is AUD.
    """

    def __init__(
        self,
        *,
        quote_date: date,
        origin: str,
        destination: str,
        chargeable_weight_kg: Decimal,
        payment_term: PaymentTerm,
        quote_currency: str,
        caf_rate: Optional[Decimal],
        policy_code: str = "",
        using: str = "default",
    ):
        if (origin, destination) not in PILOT_LANES:
            raise RateMatrixExportPricingError(
                "LANE_NOT_PILOT", f"Lane {origin}-{destination} cannot be priced by the Rate Matrix export path."
            )
        expected = PILOT_QUOTE_CURRENCIES.get(getattr(payment_term, "value", str(payment_term)))
        if expected is None or expected != quote_currency:
            raise RateMatrixExportPricingError(
                "CURRENCY_NOT_PILOT",
                f"Payment term {payment_term} with currency {quote_currency} is not a Pilot combination.",
            )
        # Margin is never applied to an explicit SELL tariff: margin_rate stays None and is never read.
        super().__init__(
            quote_date=quote_date, origin=origin, destination=destination,
            chargeable_weight_kg=chargeable_weight_kg, payment_term=payment_term, caf_rate=caf_rate,
            margin_rate=None, margin_method="MARKUP_ON_COST", destination_currency=quote_currency,
        )
        self.policy_code = policy_code
        self.using = using
        self._pair = None
        self._supplier: Optional[tuple[Any, str]] = None
        self._tariffs: dict[tuple[str, str], Optional[MatrixRate]] = {}
        self._native_sell: set[str] = set()  # SELL tariffs native in the (non-PGK) quote currency
        self._conversions: list[dict[str, Any]] = []
        self._audit: dict[str, Any] = {}

    # ---------------------------------------------------------------- lookups

    def _prefetch_rates(self, product_code_ids):
        """Only ProductCodes are loaded; no legacy rate table is read."""
        self._pc_cache = {pc.id: pc for pc in ProductCode.objects.filter(id__in=product_code_ids)}
        self._cogs_rate_cache, self._sell_rate_cache, self._surcharge_cache = {}, {}, {}

    def _lane_supplier(self):
        if self._supplier is None:
            from django.db.models import Q

            from core.geo_models import GeoLocationIdentifier
            from pricing_v4.rate_matrix_models import RateLine

            carriers = {
                (line.sheet.carrier_id, line.sheet.carrier.legal_name)
                for line in RateLine.objects.using(self.using).filter(
                    Q(applicability__origin__identifiers__code=self.origin,
                      applicability__origin__identifiers__scheme=GeoLocationIdentifier.Scheme.IATA),
                    sheet__is_active=True, sheet__rate_type=resolver.BUY, sheet__valid_from__lte=self.quote_date,
                    applicability__direction="EXPORT",
                ).filter(Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=self.quote_date))
                .select_related("sheet", "sheet__carrier")
                if line.sheet.carrier_id
            }
            if len(carriers) != 1:
                raise RateMatrixExportPricingError(
                    "SUPPLIER_NOT_SINGLE",
                    f"Rate Matrix export BUY sheets for {self.origin} name {len(carriers)} suppliers; exactly one "
                    "is required.",
                )
            self._supplier = next(iter(carriers))
        return self._supplier

    def _check_mirror(self, pc: ProductCode, tariff: resolver.ResolvedTariff) -> None:
        mirror = CommercialProductCode.objects.using(self.using).filter(code=pc.code).first()
        if mirror is None or not mirror.is_active:
            raise RateMatrixExportPricingError(
                "CPC_MISSING", f"{pc.code}: no active CommercialProductCode; the charge cannot be classified."
            )
        if mirror.gst_treatment != pc.gst_treatment:
            raise RateMatrixExportPricingError(
                "GST_TREATMENT_MISMATCH",
                f"{pc.code}: CommercialProductCode GST treatment '{mirror.gst_treatment}' differs from the "
                f"ProductCode '{pc.gst_treatment}'.",
            )
        if tariff.rate_basis == "PERCENTAGE":
            base = pc.percent_of_product_code.code if pc.percent_of_product_code_id else None
            if tariff.percentage_basis_product_code != base:
                raise RateMatrixExportPricingError(
                    "PERCENTAGE_BASIS_MISMATCH",
                    f"{pc.code}: Rate Matrix percentage basis '{tariff.percentage_basis_product_code}' differs "
                    f"from the ProductCode basis '{base}'.",
                )

    def _lookup(self, side: str, pc: ProductCode) -> Optional[MatrixRate]:
        key = (side, pc.code)
        if key in self._tariffs:
            return self._tariffs[key]
        if side == "BUY":
            supplier_id, supplier_name = self._lane_supplier()
            result = resolver.resolve(resolver.ResolutionContext(
                rate_type=resolver.BUY, direction="EXPORT", effective_date=self.quote_date, product_code=pc.code,
                origin_iata=self.origin, destination_iata=self.destination, supplier_id=supplier_id,
                chargeable_weight=self.chargeable_weight_kg,
            ), using=self.using)
        else:
            # Native SELL in the quote currency wins: used directly, no FX, no CAF, no margin. Only when none
            # exists does the locked export rule allow the PGK SELL to be converted (PGK to FCY at TT SELL).
            result = None
            if self.converts:
                result = self._resolve_sell(pc, self.quote_currency)
                if result.outcome == resolver.NO_MATCH:
                    result = None
            if result is None:
                result = self._resolve_sell(pc, "PGK")
        if result.outcome == resolver.NO_MATCH:
            self._tariffs[key] = None
            return None
        if result.outcome != resolver.EXACT_MATCH:
            raise RateMatrixExportPricingError(
                f"RESOLVER_{result.outcome}", f"{pc.code} {side}: {'; '.join(result.reasons)}"
            )
        tariff = result.tariff
        if side == "SELL" and self.converts and tariff.currency_code == self.quote_currency:
            self._check_mirror(pc, tariff)
            rate = _legacy_shaped(tariff)
            self._native_sell.add(pc.code)
            self._tariffs[key] = rate
            return rate
        if tariff.currency_code != "PGK":
            raise RateMatrixExportPricingError(
                "TARIFF_CURRENCY_NOT_PGK",
                f"{pc.code} {side}: tariff currency {tariff.currency_code}; Pilot tariffs are native PGK.",
            )
        self._check_mirror(pc, tariff)
        rate = _legacy_shaped(tariff)
        if side == "BUY":
            rate.agent = SimpleNamespace(name=tariff.supplier_name) if tariff.supplier_name else None
        self._tariffs[key] = rate
        return rate

    def _resolve_sell(self, pc: ProductCode, currency: str):
        return resolver.resolve(resolver.ResolutionContext(
            rate_type=resolver.SELL, direction="EXPORT", effective_date=self.quote_date, product_code=pc.code,
            origin_iata=self.origin, destination_iata=self.destination, quote_currency=currency,
            chargeable_weight=self.chargeable_weight_kg,
        ), using=self.using)

    def _get_cogs(self, product_code_id: int):
        pc = self._get_product_code(product_code_id)
        return None if pc is None else self._lookup("BUY", pc)

    def _get_sell_rate(self, product_code_id: int):
        pc = self._get_product_code(product_code_id)
        return None if pc is None else self._lookup("SELL", pc)

    def _calculate_amount(self, rate) -> RuleEvaluation:
        if isinstance(rate, MatrixRate) and rate.weight_breaks and any("min_charge" in b for b in rate.weight_breaks):
            # The production rule applies one minimum to the whole line. A tier minimum is evaluated here
            # with the production tier-selection and limit rule.
            return evaluate_tiered_break_rule(
                rate.weight_breaks, self.chargeable_weight_kg,
                min_amount=_selected_tier_minimum(rate, self.chargeable_weight_kg), max_amount=rate.max_charge,
            )
        return super()._calculate_amount(rate)

    # ---------------------------------------------------------------- locked conversion

    @property
    def converts(self) -> bool:
        return self.quote_currency != "PGK"

    def _fx_pair(self):
        if self._pair is None:
            # Missing, stale and ambiguous market facts raise from the resolver and fail the quote.
            pair = resolve_market_fx_pair(self.quote_currency, "PGK", self.quote_date)
            if pair.is_inverse or pair.is_cross:
                raise RateMatrixExportPricingError(
                    "FX_NOT_DIRECT",
                    f"{self.quote_currency}/PGK resolved only as an inverse or cross pair; the locked export rule "
                    f"requires the stored {self.quote_currency}/PGK TT SELL.",
                )
            age = (self.quote_date - pair.effective_date).days
            if age < 0 or age > MAX_FX_AGE_DAYS:
                raise StaleFxMarketRateError(
                    f"{self.quote_currency}/PGK rate dated {pair.effective_date} is {age} days old on "
                    f"{self.quote_date}; the export maximum is {MAX_FX_AGE_DAYS} days."
                )
            if pair.tt_sell is None or pair.tt_sell <= 0:
                raise RateMatrixExportPricingError("FX_NOT_POSITIVE", "TT SELL must be strictly positive.")
            self._pair = pair
        return self._pair

    def _to_quote_currency(self, pgk: Decimal, product_code: str) -> tuple[Decimal, bool]:
        """(amount in the quote currency, converted?). PGK needs no FX and no CAF; zero converts to zero."""
        if not self.converts or pgk == 0:
            return (pgk if not self.converts else Decimal("0.00")), False
        if self.caf_rate is None:
            raise MissingCommercialPolicyError(
                "Export CAF rate is required when a currency conversion occurs; calculation fails closed."
            )
        pair = self._fx_pair()
        # BSP: PGK to FCY uses TT SELL. Stored PGK per FCY, so FCY = PGK / TT SELL (= PGK x published TT Sell).
        pure = _money(pgk / pair.tt_sell)
        commercial = _money(pure * (Decimal("1") + self.caf_rate))
        self._conversions.append({
            "product_code": product_code, "role": "SELL", "from_currency": "PGK", "to_currency": self.quote_currency,
            "amount_in": str(pgk), "pure_market_amount": str(pure), "caf_percent": str(self.caf_rate * 100),
            "caf_amount": str(commercial - pure), "commercial_amount": str(commercial),
            "caf_operation": fx_conventions.CAF_OPERATION_FROM_PGK,
            "caf_method": CAF_METHOD, "fx_side_convention": FX_SIDE_CONVENTION,
            "legs": [{
                "pair": f"{self.quote_currency}/PGK", "side": fx_conventions.SIDE_PGK_TO_FCY, "rate": str(pair.tt_sell),
                "source": pair.source, "source_role": pair.source_role,
                "effective_date": pair.effective_date.isoformat(), "age_days": (self.quote_date - pair.effective_date).days,
                "max_age_days": min(pair.max_age_days, MAX_FX_AGE_DAYS) if pair.max_age_days is not None else MAX_FX_AGE_DAYS,
                "policy_code": pair.policy_code, "is_inverse": pair.is_inverse, "is_cross": pair.is_cross,
            }],
        })
        return commercial, True

    # ---------------------------------------------------------------- lines

    def _classify(self, pc: ProductCode):
        return get_png_gst_category(
            product_code=pc, shipment_type="EXPORT", leg="ORIGIN", standard_rate=self._standard_gst_rate
        )

    def _line(self, pc: ProductCode, *, cogs, sell_pgk: Decimal, cost: RuleEvaluation, sell_rule: str,
              note: str = "", cost_source: Optional[str] = None, rate_missing: bool = False,
              description: Optional[str] = None, native: bool = False):
        """Build one line. ``native`` means ``sell_pgk`` is already a native quote-currency SELL amount:
        it is used directly (no FX, no CAF, no margin) and has no PGK equivalent."""
        gst_category, gst_rate = self._classify(pc)
        if native:
            sell_amount, converted = sell_pgk, False
        else:
            sell_amount, converted = self._to_quote_currency(sell_pgk, pc.code)
        gst_amount = _money(sell_amount * gst_rate)
        gst_pgk = _money(sell_pgk * gst_rate)
        # Margin is reported only when sell and cost share a currency (cost is PGK).
        margin = Decimal("0") if native else sell_pgk - cost.amount
        agent = getattr(cogs, "agent", None)
        line = ChargeLineResult(
            product_code_id=pc.id, product_code=pc.code, description=description or pc.description,
            category=pc.category, cost_amount=cost.amount, cost_currency="PGK",
            cost_source=cost_source or ("COGS" if cogs else "N/A"), agent_name=agent.name if agent else None,
            sell_amount=sell_amount, sell_currency=self.quote_currency, margin_amount=margin,
            margin_percent=(margin / cost.amount * 100 if cost.amount > 0 else Decimal("0")),
            gst_category=gst_category, gst_rate=gst_rate, gst_amount=gst_amount,
            sell_incl_gst=sell_amount + gst_amount, is_rate_missing=rate_missing, notes=note,
            fx_applied=converted, caf_applied=converted, margin_applied=False, rule_family=sell_rule,
        )
        if native:
            return line, None, None
        return line, sell_pgk, sell_pgk + gst_pgk

    def _regular_line(self, pc_id: int, requested: list[int]):
        pc = self._get_product_code(pc_id)
        if pc is None:
            return None
        cogs = self._get_cogs(pc_id)
        sell_rate = self._get_sell_rate(pc_id)
        cost = self._calculate_amount(cogs) if cogs else RuleEvaluation(CALCULATION_FLAT, Decimal("0.00"))
        if sell_rate is None:
            if pc_id not in requested:
                return None
            gst_category, gst_rate = self._classify(pc)
            line = ChargeLineResult(
                product_code_id=pc.id, product_code=pc.code, description=pc.description, category=pc.category,
                cost_amount=cost.amount, cost_currency="PGK", cost_source="COGS" if cogs else "N/A",
                agent_name=cogs.agent.name if cogs is not None and cogs.agent else None,
                sell_amount=Decimal("0"), sell_currency=self.quote_currency, margin_amount=Decimal("0"),
                margin_percent=Decimal("0"), gst_category=gst_category, gst_rate=gst_rate,
                gst_amount=Decimal("0"), sell_incl_gst=Decimal("0"), is_rate_missing=True,
                notes=f"Requested sell rate missing for {pc.code}", rule_family=cost.rule_family,
            )
            return line, Decimal("0.00"), Decimal("0.00"), cost.amount
        sell = self._calculate_amount(sell_rate)
        line, sell_pgk, sell_pgk_incl = self._line(
            pc, cogs=cogs, sell_pgk=sell.amount, cost=cost,
            sell_rule=sell.rule_family if sell.amount > 0 else cost.rule_family,
            native=pc.code in self._native_sell,
        )
        return line, sell_pgk, sell_pgk_incl, cost.amount

    def _percentage_line(
        self, pc_id: int, sell_base: dict[int, tuple[Decimal, str]], cost_base: dict[int, Decimal]
    ):
        pc = self._get_product_code(pc_id)
        base_pc = pc.percent_of_product_code if pc else None
        if not pc or not base_pc:
            return None
        sell_rate = self._get_sell_rate(pc_id)
        if not sell_rate or not sell_rate.percent_rate:
            return None
        native = pc.code in self._native_sell
        currency = self.quote_currency if native else "PGK"
        base_sell, base_currency = sell_base.get(base_pc.id, (Decimal("0"), currency))
        if base_currency != currency:
            # A percentage is computed in one currency. A native FCY dependant on a PGK base (or the
            # reverse) would need a conversion no rule approves, so it fails closed.
            raise RateMatrixExportPricingError(
                "NATIVE_CURRENCY_MIX",
                f"{pc.code} SELL is {currency} but its base {base_pc.code} is {base_currency}.",
            )
        base_cost = cost_base.get(base_pc.id, Decimal("0"))
        sell = evaluate_percent_of_base_rule(sell_rate.percent_rate, base_sell)
        cost = evaluate_percent_of_base_rule(sell_rate.percent_rate, base_cost)
        line, sell_pgk, sell_pgk_incl = self._line(
            pc, cogs=None, sell_pgk=sell.amount, cost=cost, sell_rule=CALCULATION_PERCENT_OF_BASE,
            note=f"Based on {base_pc.code}: {currency} {base_sell}", cost_source=f"{sell_rate.percent_rate}% of COGS",
            description=f"{pc.description} ({sell_rate.percent_rate}% of {base_pc.code})", native=native,
        )
        return line, sell_pgk, sell_pgk_incl, cost.amount

    def calculate_quote(
        self, product_code_ids, is_dg: bool = False, service_scope: str = "P2P",
        commodity_code: str = DEFAULT_COMMODITY_CODE,
    ) -> QuoteResult:
        if is_dg or commodity_code != DEFAULT_COMMODITY_CODE:
            raise RateMatrixExportPricingError(
                "SCOPE_NOT_PILOT", "Only General Cargo that is not dangerous goods is Rate Matrix priced."
            )
        if service_scope == "A2A":
            service_scope = "P2P"
        if service_scope not in ("P2P", "D2A"):
            raise RateMatrixExportPricingError("SCOPE_NOT_PILOT", f"Service scope {service_scope} is not a Pilot scope.")

        self._prefetch_rates(product_code_ids)
        term = self.payment_term.value if hasattr(self.payment_term, "value") else str(self.payment_term)
        requested = self.get_requested_product_code_ids(
            is_dg=is_dg, service_scope=service_scope, commodity_code=commodity_code, origin=self.origin,
            destination=self.destination, payment_term=term, quote_date=self.quote_date,
        )
        regular, percent = [], []
        for pc_id in product_code_ids:
            pc = self._get_product_code(pc_id)
            (percent if pc and pc.default_unit == ProductCode.UNIT_PERCENT else regular).append(pc_id)

        # Dependants (percentage-of-product) are computed on the native tariff amounts (PGK, or the quote
        # currency for a native FCY SELL) and then converted if PGK, so a converted base never feeds a second
        # conversion.
        sell_base: dict[int, tuple[Decimal, str]] = {}
        cost_base: dict[int, Decimal] = {}
        built: list[tuple[ChargeLineResult, Decimal, Decimal, Decimal]] = []
        for pc_id in regular:
            item = self._regular_line(pc_id, requested)
            if item is None:
                continue
            built.append(item)
            sell_base[pc_id] = (item[0].sell_amount, self.quote_currency) if item[1] is None else (item[1], "PGK")
            cost_base[pc_id] = item[3]
        for pc_id in percent:
            item = self._percentage_line(pc_id, sell_base, cost_base)
            if item is not None:
                built.append(item)

        line_items = []
        for line, sell_pgk, sell_pgk_incl, cost_pgk in built:
            item = self._to_quote_line_item(line)
            item.cost_pgk, item.sell_pgk, item.sell_pgk_incl_gst = cost_pgk, sell_pgk, sell_pgk_incl
            line_items.append(item)
        lines = [entry[0] for entry in built]

        total_cost_pgk = sum((i.cost_pgk or Decimal("0.00") for i in line_items), Decimal("0.00"))
        total_sell_pgk = sum((i.sell_pgk or Decimal("0.00") for i in line_items), Decimal("0.00"))
        pair = self._pair
        self._audit = {
            "path": PRICING_PATH, "policy_code": self.policy_code, "quote_currency": self.quote_currency,
            "lane": f"{self.origin}-{self.destination}", "service_scope": service_scope,
            "chargeable_weight_kg": str(self.chargeable_weight_kg), "margin_applied_to_explicit_sell": False,
            "tariffs": [
                _tariff_provenance(side, rate.tariff)
                for (side, _code), rate in sorted(self._tariffs.items(), key=lambda kv: (kv[0][1], kv[0][0]))
                if rate is not None
            ],
            "missing_tariffs": sorted(f"{side}:{code}" for (side, code), rate in self._tariffs.items() if rate is None),
            # Precedence: a native SELL in the quote currency is used as is; otherwise the PGK SELL is
            # converted under the locked export rule (the only conversion this path allows).
            "native_quote_currency_sell": sorted(self._native_sell),
        }
        return QuoteResult(
            line_items=line_items, total_cost_pgk=total_cost_pgk, total_sell_pgk=total_sell_pgk,
            fx_applied=bool(self._conversions),
            tax_breakdown=build_tax_breakdown(line_items, converter=lambda amount, currency: amount),
            origin=self.origin, destination=self.destination, quote_date=self.quote_date,
            chargeable_weight_kg=self.chargeable_weight_kg, direction="EXPORT", payment_term=term,
            service_scope=service_scope, currency=self.quote_currency, quote_currency=self.quote_currency,
            total_margin=sum((line.margin_amount for line in lines), Decimal("0")),
            total_gst=sum((line.gst_amount for line in lines), Decimal("0")),
            total_sell_incl_gst=sum((line.sell_incl_gst for line in lines), Decimal("0")),
            fx_rate_used=pair.tt_sell if pair is not None else None, effective_fx_rate=None,
            caf_rate=self.caf_rate if self._conversions else None,
            audit_metadata={
                "commercial_convention": {
                    "caf_method": CAF_METHOD, "fx_side_convention": FX_SIDE_CONVENTION,
                    "margin_on_explicit_sell": False,
                },
                "conversions": list(self._conversions),
                "pgk_equivalent_complete": all(i.sell_pgk is not None or not i.sell_amount for i in line_items),
                "rate_matrix_export": self._audit,
            },
        )
