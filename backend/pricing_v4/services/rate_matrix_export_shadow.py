"""Export commercial shadow pricing (Pilot Gate B3M-C).

Read-only comparison, for Pilot export lanes (POM to BNE / SYD, AIR, direct, General Cargo), of:

- **legacy**: the unmodified production ``ExportPricingEngine`` pricing from ``ExportCOGS``,
  ``ExportSellRate``, ``LocalCOGSRate`` and ``LocalSellRate`` rows in PGK; and
- **matrix**: the same engine with only its two rate lookups redirected to Rate Matrix tariffs.

Everything downstream of the lookup (rate rules, tier selection, minimums and caps, percentage
dependants, GST classification) is production code. Nothing here is imported by any quote path.

Locked commercial rules (Commercial Manager, 2026-10-12) that this harness proves, in this module only:

- Export SELL tariffs are **PGK only**. No AUD SELL tariff exists or is created.
- A PGK quote has no conversion, so it needs no FX and carries no CAF.
- An AUD quote converts each explicit PGK SELL line once: ``AUD = (PGK / TT BUY) * (1 + export CAF)``,
  FX from ``FxMarketRate`` through the policy-driven resolver (source priority, age limit, fail closed).
  The CAF is a separate uplift after pure FX and is applied only because a conversion occurred.
- An explicit SELL tariff receives no additional margin.

The production export engine does not yet implement these conventions (it applies margin, then divides
by TT SELL x (1 + CAF) for COLLECT). That gap is reported per AUD scenario as ``NOT_COMPARABLE``; this
module does not change production behaviour.

Safety: diagnostic only; runs in a read-only, rolled-back transaction; writes nothing; invents no rate,
FX, CAF or margin; any missing, stale or ambiguous input is ``BLOCKED`` for the scenario.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm
from pricing_v4.models import ProductCode
from pricing_v4.services import rate_matrix_resolver as resolver
from pricing_v4.services.commercial_policy import (
    MissingCommercialPolicyError,
    PolicyResolutionError,
    require_unique_commercial_terms_policy,
)
from pricing_v4.services.fx_resolver import FxResolutionError, resolve_market_fx_pair
from pricing_v4.services.rate_matrix_manifest import read_only_database

MATCH = "MATCH"
EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"
BLOCKED = "BLOCKED"
NOT_COMPARABLE = "NOT_COMPARABLE"
CLASSIFICATIONS = (MATCH, EXPECTED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, BLOCKED, NOT_COMPARABLE)

DEFAULT_LANES = (("POM", "BNE"), ("POM", "SYD"))
DEFAULT_WEIGHTS = tuple(Decimal(w) for w in ("30", "45", "100", "200", "500", "999", "1000", "1001"))
DEFAULT_SCOPES = ("A2A", "D2A")
DEFAULT_CURRENCIES = ("PGK", "AUD")
SUPPLIER_CODE = "PX"
NOT_APPROVED = "EXPORT CAF AND CONVENTIONS PER LOCKED RULE 2026-10-12. NOT LIVE. NOT WIRED INTO PRODUCTION."

# Charges whose locked BUY rule cannot be expressed by a Rate Matrix line, so no BUY line is loaded and the
# legacy database value is not comparable to it. See docs/b3m-c-export-manifest.md.
BUY_NOT_REPRESENTABLE = {
    "EXP-BUILDUP": (
        "Locked BUY build-up has a tier-conditional minimum (0-99 kg nil; 100 kg and over K0.10/kg or K0.15/kg "
        "with K30 minimum). A line carries one minimum for every tier, so no BUY line is loaded; the legacy "
        "database row (0.15/kg, K30 at every weight) is superseded by the locked rule."
    ),
}


class ExportShadowBlocked(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Line:
    product_code: str
    sell_amount: Decimal
    gst_amount: Decimal
    sell_incl_gst: Decimal
    cost_amount: Decimal
    cost_currency: str
    gst_category: str
    gst_rate: Decimal
    is_rate_missing: bool = False
    provenance: str = ""
    conversion: dict[str, Any] | None = None


@dataclass
class Priced:
    lines: dict[str, Line]
    totals: dict[str, Decimal]
    currency: str
    conversions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Scenario:
    lane: str
    weight: Decimal
    scope: str
    currency: str

    @property
    def key(self) -> str:
        return f"{self.weight.normalize():f}kg|{self.scope}|{self.currency}"

    @property
    def origin(self) -> str:
        return self.lane.split("-")[0]

    @property
    def destination(self) -> str:
        return self.lane.split("-")[1]


@dataclass
class Record:
    lane: str
    scenario: str
    product_code: str
    aspect: str
    classification: str
    legacy: str | None = None
    shadow: str | None = None
    currency: str = ""
    provenance: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ExportShadowReport:
    quote_date: date
    records: list[Record] = field(default_factory=list)
    policy: dict[str, Any] | None = None
    fx_provenance: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {name: sum(1 for r in self.records if r.classification == name) for name in CLASSIFICATIONS}

    @property
    def unexplained(self) -> list[Record]:
        return [r for r in self.records if r.classification == UNEXPLAINED_DIFFERENCE]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "SHADOW_EXPORT", "writes_performed": 0, "quote_date": self.quote_date.isoformat(),
            "counts": self.counts(), "policy_provenance": self.policy, "fx_provenance": self.fx_provenance,
            "notes": self.notes, "records": [r.as_dict() for r in self.records],
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True, default=str)

    def render_text(self, *, show_matches: bool = False) -> str:
        counts = self.counts()
        out = [
            "Rate Matrix export shadow pricing (diagnostic only; no quote is affected)",
            f"Quote date: {self.quote_date.isoformat()}",
            "   ".join(f"{name} {counts[name]}" for name in CLASSIFICATIONS),
            f"Status: {NOT_APPROVED}",
        ]
        out += [f"Note: {note}" for note in self.notes]
        for r in self.records:
            if r.classification == MATCH and not show_matches:
                continue
            out.append(
                f"  {r.classification:22s} {r.lane} [{r.scenario}] {r.product_code} {r.aspect}: "
                f"legacy={r.legacy} shadow={r.shadow} {r.currency}"
            )
            if r.provenance:
                out.append(f"      provenance: {r.provenance}")
            if r.reason:
                out.append(f"      reason: {r.reason}")
        out += ["", "Writes performed: 0"]
        return "\n".join(out)


# ----------------------------------------------------------------------------- Rate Matrix lookup


@dataclass
class ShadowRate:
    """A Rate Matrix tariff shaped like the legacy rate records the export engine evaluates."""

    currency: str
    rate_type: str = ""
    amount: Decimal | None = None
    percent_rate: Decimal | None = None
    rate_per_kg: Decimal | None = None
    rate_per_shipment: Decimal | None = None
    min_charge: Decimal | None = None
    max_charge: Decimal | None = None
    weight_breaks: list | None = None
    is_additive: bool = False
    agent: Any = None
    provenance: str = ""


def _shadow_rate(tariff: resolver.ResolvedTariff, *, supplier: str | None) -> ShadowRate:
    rate = ShadowRate(
        currency=tariff.currency_code, min_charge=tariff.min_charge, max_charge=tariff.max_charge,
        agent=SimpleNamespace(name=supplier) if supplier else None,
        provenance=f"{tariff.sheet_name} v{tariff.sheet_version} line {tariff.line_id}",
    )
    basis = tariff.rate_basis
    if basis == "FLAT":
        rate.rate_type, rate.amount, rate.rate_per_shipment = "FIXED", tariff.unit_rate, tariff.unit_rate
    elif basis == "PER_KG":
        rate.rate_type, rate.amount, rate.rate_per_kg = "PER_KG", tariff.unit_rate, tariff.unit_rate
        if tariff.additive_flat_amount is not None:
            rate.is_additive, rate.rate_per_shipment = True, tariff.additive_flat_amount
    elif basis == "TIERED_WEIGHT":
        rate.weight_breaks = [
            {"min_kg": str(tier.min_quantity), "rate": str(tier.unit_rate)} for tier in tariff.tiers
        ]
    elif basis == "PERCENTAGE":
        rate.rate_type, rate.amount, rate.percent_rate = "PERCENT", tariff.percentage_rate, tariff.percentage_rate
    else:  # pragma: no cover - the contract has no other basis
        raise ExportShadowBlocked("UNSUPPORTED_BASIS", f"Rate basis {basis} is not supported by the shadow.")
    return rate


class _MatrixLookup:
    """Resolves PGK Rate Matrix tariffs for one scenario. Fails closed on anything that is not exact."""

    def __init__(self, scenario: Scenario, quote_date: date, using: str):
        self.s, self.quote_date, self.using = scenario, quote_date, using
        self._cache: dict[tuple[str, str], ShadowRate | None] = {}
        self._supplier: tuple[Any, str] | None = None

    def _supplier_for_lane(self):
        if self._supplier is None:
            from django.db.models import Q

            from core.geo_models import GeoLocationIdentifier
            from pricing_v4.rate_matrix_models import RateLine

            carriers = {
                (line.sheet.carrier_id, line.sheet.carrier.legal_name)
                for line in RateLine.objects.using(self.using).filter(
                    Q(applicability__origin__identifiers__code=self.s.origin,
                      applicability__origin__identifiers__scheme=GeoLocationIdentifier.Scheme.IATA),
                    sheet__is_active=True, sheet__rate_type=resolver.BUY, sheet__valid_from__lte=self.quote_date,
                    applicability__direction="EXPORT",
                ).filter(Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=self.quote_date))
                .select_related("sheet", "sheet__carrier")
                if line.sheet.carrier_id
            }
            if len(carriers) != 1:
                raise ExportShadowBlocked(
                    "SUPPLIER_NOT_SINGLE",
                    f"Rate Matrix export BUY sheets for {self.s.origin} name {len(carriers)} suppliers; exactly one "
                    "is required.",
                )
            self._supplier = next(iter(carriers))
        return self._supplier

    def _check_mirror(self, pc: ProductCode, tariff: resolver.ResolvedTariff) -> None:
        mirror = CommercialProductCode.objects.using(self.using).filter(code=pc.code).first()
        if mirror is not None and mirror.gst_treatment != pc.gst_treatment:
            raise ExportShadowBlocked(
                "GST_TREATMENT_MISMATCH",
                f"{pc.code}: CommercialProductCode GST treatment '{mirror.gst_treatment}' differs from the "
                f"legacy ProductCode '{pc.gst_treatment}'.",
            )
        if tariff.rate_basis == "PERCENTAGE":
            legacy_base = pc.percent_of_product_code.code if pc.percent_of_product_code_id else None
            if tariff.percentage_basis_product_code != legacy_base:
                raise ExportShadowBlocked(
                    "PERCENTAGE_BASIS_MISMATCH",
                    f"{pc.code}: Rate Matrix percentage basis '{tariff.percentage_basis_product_code}' differs "
                    f"from the legacy basis '{legacy_base}'.",
                )

    def _resolve(self, pc: ProductCode, context: resolver.ResolutionContext, supplier: str | None):
        result = resolver.resolve(context, using=self.using)
        if result.outcome == resolver.NO_MATCH:
            return None
        if result.outcome != resolver.EXACT_MATCH:
            raise ExportShadowBlocked(
                f"RESOLVER_{result.outcome}", f"{pc.code}: {result.outcome}: {'; '.join(result.reasons)}"
            )
        self._check_mirror(pc, result.tariff)
        return _shadow_rate(result.tariff, supplier=supplier)

    def buy(self, pc: ProductCode) -> ShadowRate | None:
        if pc.code in BUY_NOT_REPRESENTABLE:
            return None
        key = ("BUY", pc.code)
        if key not in self._cache:
            supplier_id, supplier_name = self._supplier_for_lane()
            self._cache[key] = self._resolve(pc, resolver.ResolutionContext(
                rate_type=resolver.BUY, direction="EXPORT", effective_date=self.quote_date, product_code=pc.code,
                origin_iata=self.s.origin, destination_iata=self.s.destination, supplier_id=supplier_id,
                chargeable_weight=self.s.weight,
            ), supplier_name)
        return self._cache[key]

    def sell(self, pc: ProductCode) -> ShadowRate | None:
        key = ("SELL", pc.code)
        if key not in self._cache:
            # PGK native tariffs only. A payment term is not part of the lookup: export SELL tariffs are
            # term-independent and the resolver treats a blank applicability as ANY.
            self._cache[key] = self._resolve(pc, resolver.ResolutionContext(
                rate_type=resolver.SELL, direction="EXPORT", effective_date=self.quote_date,
                product_code=pc.code, origin_iata=self.s.origin, destination_iata=self.s.destination,
                quote_currency="PGK", chargeable_weight=self.s.weight,
            ), None)
        return self._cache[key]


class MatrixShadowExportEngine(ExportPricingEngine):
    """The production export engine with only its two rate lookups redirected to the Rate Matrix."""

    def __init__(self, *, matrix: _MatrixLookup, **kwargs):
        super().__init__(**kwargs)
        self._matrix = matrix

    def _get_cogs(self, product_code_id: int):
        pc = self._get_product_code(product_code_id)
        return self._matrix.buy(pc) if pc else None

    def _get_sell_rate(self, product_code_id: int):
        pc = self._get_product_code(product_code_id)
        return self._matrix.sell(pc) if pc else None


# ----------------------------------------------------------------------------- orchestration


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_pgk_to_aud(amount: Decimal, tt_buy: Decimal, caf_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Locked export rule: pure FX at TT BUY first (rounded), then the CAF as a separate uplift (rounded).

    Returns (pure, caf, commercial). The CAF is never folded into the rate.
    """
    if amount == 0:
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
    if tt_buy <= 0:
        raise ExportShadowBlocked("FX_NOT_POSITIVE", "TT BUY must be strictly positive.")
    pure = _q(amount / tt_buy)
    commercial = _q(pure * (Decimal("1") + caf_rate))
    return pure, commercial - pure, commercial


class _ExportShadow:
    def __init__(self, quote_date, lanes, weights, scopes, currencies, using):
        self.quote_date, self.lanes, self.weights = quote_date, tuple(lanes), tuple(weights)
        self.scopes, self.currencies, self.using = tuple(scopes), tuple(currencies), using
        self.report = ExportShadowReport(quote_date=quote_date)
        self._fx_seen: dict[str, dict[str, Any]] = {}
        self._pgk_cache: dict[tuple[str, Decimal, str], tuple[Priced, Priced] | ExportShadowBlocked] = {}

    # ---------------------------------------------------------------- policy

    def _policy(self):
        policy = require_unique_commercial_terms_policy(self.quote_date)
        if policy.export_caf_rate is None:
            raise ExportShadowBlocked("POLICY_INCOMPLETE", f"Policy {policy.policy_code} has no export CAF.")
        self.report.policy = {
            "status": NOT_APPROVED, "policy_code": policy.policy_code,
            "valid_from": policy.valid_from.isoformat(),
            "valid_until": policy.valid_until.isoformat() if policy.valid_until else None,
            "export_caf_percent": str(policy.export_caf_percent), "gst_standard_percent": str(policy.gst_standard_percent),
            "fx_max_age_days": policy.fx_max_age_days, "fx_primary_source": policy.fx_primary_source,
            "fx_fallback_source": policy.fx_fallback_source,
            "margin_applied_to_explicit_sell": False,
        }
        return policy

    def run(self) -> ExportShadowReport:
        try:
            policy = self._policy()
        except (ExportShadowBlocked, PolicyResolutionError, FxResolutionError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            for scenario in self._all_scenarios():
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{code}: {exc}")
            return self.report
        for scenario in self._all_scenarios():
            self._scenario(scenario, policy)
        return self.report

    def _all_scenarios(self):
        for origin, destination in self.lanes:
            for weight in self.weights:
                for scope in self.scopes:
                    for currency in self.currencies:
                        yield Scenario(f"{origin}-{destination}", weight, scope, currency)

    # ---------------------------------------------------------------- pricing

    def _price_pgk(self, engine_class, scenario: Scenario, *, matrix: bool) -> Priced:
        kwargs = {
            "quote_date": self.quote_date, "origin": scenario.origin, "destination": scenario.destination,
            "chargeable_weight_kg": scenario.weight, "payment_term": PaymentTerm.PREPAID,
            "caf_rate": None, "margin_rate": None, "margin_method": "MARKUP_ON_COST",
            "destination_currency": "PGK",
        }
        if matrix:
            kwargs["matrix"] = _MatrixLookup(scenario, self.quote_date, self.using)
        engine = engine_class(**kwargs)
        ids = ExportPricingEngine.get_product_codes(
            is_dg=False, service_scope=scenario.scope, origin=scenario.origin, destination=scenario.destination,
            payment_term="PREPAID", quote_date=self.quote_date,
        )
        result = engine.calculate_quote(ids, service_scope=scenario.scope)
        lines: dict[str, Line] = {}
        for item in result.line_items:
            sell_rate = None
            if matrix:
                sell_rate = engine._matrix._cache.get(("SELL", item.product_code))
            lines[item.product_code] = Line(
                product_code=item.product_code, sell_amount=item.sell_amount, gst_amount=item.gst_amount,
                sell_incl_gst=item.sell_incl_gst, cost_amount=item.cost_amount, cost_currency=item.cost_currency,
                gst_category=item.gst_category, gst_rate=item.gst_rate,
                is_rate_missing=bool(getattr(item, "is_rate_missing", False)),
                provenance=sell_rate.provenance if sell_rate is not None else "",
            )
        return Priced(lines, _totals(lines), "PGK")

    def _pgk_pair(self, scenario: Scenario) -> tuple[Priced, Priced]:
        """Legacy and matrix PGK pricing for a scenario's lane, weight and scope (shared across currencies)."""
        key = (scenario.lane, scenario.weight, scenario.scope)
        if key not in self._pgk_cache:
            try:
                legacy = self._price_pgk(ExportPricingEngine, scenario, matrix=False)
                shadow = self._price_pgk(MatrixShadowExportEngine, scenario, matrix=True)
                self._pgk_cache[key] = (legacy, shadow)
            except ExportShadowBlocked as blocked:
                self._pgk_cache[key] = blocked
        cached = self._pgk_cache[key]
        if isinstance(cached, ExportShadowBlocked):
            raise cached
        return cached

    def _to_aud(self, priced: Priced, policy, tt_buy: Decimal) -> Priced:
        """Apply the locked conversion to every explicit PGK SELL line. No margin; GST on the converted amount."""
        converted: dict[str, Line] = {}
        conversions: list[dict[str, Any]] = []
        caf = policy.export_caf_rate
        for code, line in priced.lines.items():
            pure, caf_amount, commercial = convert_pgk_to_aud(line.sell_amount, tt_buy, caf)
            gst = _q(commercial * line.gst_rate)
            evidence = None
            if line.sell_amount != 0:
                evidence = {
                    "product_code": code, "role": "SELL", "from_currency": "PGK", "to_currency": "AUD",
                    "amount_in": str(line.sell_amount), "pure_market_amount": str(pure),
                    "caf_percent": str(caf * 100), "caf_amount": str(caf_amount), "commercial_amount": str(commercial),
                    "side": "TT_BUY",
                }
                conversions.append(evidence)
            converted[code] = Line(
                product_code=code, sell_amount=commercial, gst_amount=gst, sell_incl_gst=commercial + gst,
                cost_amount=line.cost_amount, cost_currency=line.cost_currency, gst_category=line.gst_category,
                gst_rate=line.gst_rate, is_rate_missing=line.is_rate_missing, provenance=line.provenance,
                conversion=evidence,
            )
        return Priced(converted, _totals(converted), "AUD", conversions)

    def _fx(self, policy) -> Any:
        pair = resolve_market_fx_pair("AUD", "PGK", self.quote_date)
        if pair.is_inverse or pair.is_cross:
            # The locked rule names TT BUY of the stored AUD/PGK market fact. A rate that exists only as the
            # reverse pair, or only through a cross, is never inferred into it.
            raise ExportShadowBlocked(
                "FX_NOT_DIRECT",
                "AUD/PGK resolved only as an inverse or cross pair; the locked export rule requires the stored "
                "AUD/PGK TT BUY.",
            )
        info = {
            "pair": "AUD/PGK", "side": "TT_BUY", "rate": str(pair.tt_buy), "source": pair.source,
            "source_role": pair.source_role, "effective_date": pair.effective_date.isoformat(),
            "age_days": pair.age_days, "max_age_days": pair.max_age_days, "policy_code": pair.policy_code,
            "export_caf_percent": str(policy.export_caf_percent), "status": NOT_APPROVED,
        }
        self._fx_seen["AUD/PGK"] = info
        self.report.fx_provenance = sorted(self._fx_seen.values(), key=lambda i: i["pair"])
        return pair

    def _scenario(self, s: Scenario, policy) -> None:
        try:
            legacy, shadow = self._pgk_pair(s)
            if s.currency == "AUD":
                pair = self._fx(policy)
                legacy, shadow = self._to_aud(legacy, policy, pair.tt_buy), self._to_aud(shadow, policy, pair.tt_buy)
            elif s.currency != "PGK":
                raise ExportShadowBlocked("CURRENCY_UNSUPPORTED", f"Currency {s.currency} has no approved export rule.")
        except ExportShadowBlocked as blocked:
            self._emit(s, "-", "scenario", BLOCKED, reason=f"{blocked.code}: {blocked.message}")
            return
        except FxResolutionError as exc:
            self._emit(s, "-", "scenario", BLOCKED, reason=f"{type(exc).__name__}: {exc}")
            return
        except (MissingCommercialPolicyError, ValueError) as exc:
            self._emit(s, "-", "scenario", BLOCKED, reason=f"{type(exc).__name__}: {exc}")
            return
        self._compare(s, legacy, shadow)
        if s.currency == "AUD":
            self._production_note(s, shadow)

    # ---------------------------------------------------------------- comparison

    def _emit(self, s: Scenario, code: str, aspect: str, classification: str, legacy=None, shadow=None,
              currency="", provenance="", reason="") -> None:
        policy = self.report.policy
        text = provenance
        if policy and s.currency == "AUD" and classification != BLOCKED:
            text = (text + "; " if text else "") + f"policy {policy['policy_code']}"
        if self._fx_seen and s.currency == "AUD" and classification != BLOCKED:
            text += "; FX " + ", ".join(
                f"{i['pair']} {i['side']} {i['source']} {i['effective_date']}" for i in self._fx_seen.values()
            )
        self.report.records.append(Record(
            s.lane, s.key, code, aspect, classification,
            None if legacy is None else str(legacy), None if shadow is None else str(shadow), currency, text, reason,
        ))

    def _compare(self, s: Scenario, legacy: Priced, shadow: Priced) -> None:
        any_unexplained = False
        cost_not_comparable = False
        for code in sorted(set(legacy.lines) | set(shadow.lines)):
            left, right = legacy.lines.get(code), shadow.lines.get(code)
            if left is None or right is None:
                present = right if left is None else left
                self._emit(s, code, "presence", UNEXPLAINED_DIFFERENCE, "absent" if left is None else "present",
                           "present" if left is None else "absent", legacy.currency, present.provenance,
                           f"charge {'added' if left is None else 'dropped'} before pricing")
                any_unexplained = True
                continue
            for aspect in ("sell_amount", "gst_amount", "sell_incl_gst"):
                a, b = getattr(left, aspect), getattr(right, aspect)
                if a == b:
                    self._emit(s, code, aspect, MATCH, a, b, legacy.currency, right.provenance)
                else:
                    any_unexplained = True
                    self._emit(s, code, aspect, UNEXPLAINED_DIFFERENCE, a, b, legacy.currency, right.provenance,
                               "Rate Matrix tariff does not reproduce the legacy native tariff.")
            if left.cost_amount == right.cost_amount:
                if left.cost_amount != 0:
                    self._emit(s, code, "cost_amount", MATCH, left.cost_amount, right.cost_amount,
                               left.cost_currency, "BUY rate lookup (native PGK)")
            elif code in BUY_NOT_REPRESENTABLE:
                cost_not_comparable = True
                self._emit(s, code, "cost_amount", NOT_COMPARABLE, left.cost_amount, right.cost_amount,
                           left.cost_currency, "BUY rate lookup (native PGK)", BUY_NOT_REPRESENTABLE[code])
            else:
                any_unexplained = True
                self._emit(s, code, "cost_amount", UNEXPLAINED_DIFFERENCE, left.cost_amount, right.cost_amount,
                           left.cost_currency, "BUY rate lookup (native PGK)",
                           "Rate Matrix BUY tariff does not reproduce the legacy native cost.")
        for name in ("total_sell", "total_gst", "total_sell_incl_gst", "total_cost_pgk"):
            a, b = legacy.totals[name], shadow.totals[name]
            ccy = "PGK" if name == "total_cost_pgk" else legacy.currency
            if a == b:
                self._emit(s, "TOTAL", name, MATCH, a, b, ccy, "totals")
            elif name == "total_cost_pgk" and cost_not_comparable and not any_unexplained:
                self._emit(s, "TOTAL", name, NOT_COMPARABLE, a, b, ccy, "totals",
                           "Includes a BUY charge that the Rate Matrix cannot represent.")
            else:
                self._emit(s, "TOTAL", name, UNEXPLAINED_DIFFERENCE, a, b, ccy, "totals",
                           "A contributing line difference is unexplained." if any_unexplained
                           else "No explained difference accounts for this total.")

    def _production_note(self, s: Scenario, approved: Priced) -> None:
        """The production COLLECT engine does not implement the locked AUD rule; report, never reconcile."""
        try:
            engine = ExportPricingEngine(
                quote_date=self.quote_date, origin=s.origin, destination=s.destination,
                chargeable_weight_kg=s.weight, payment_term=PaymentTerm.COLLECT, destination_currency="AUD",
            )
            ids = ExportPricingEngine.get_product_codes(
                is_dg=False, service_scope=s.scope, origin=s.origin, destination=s.destination,
                payment_term="COLLECT", quote_date=self.quote_date,
            )
            result = engine.calculate_quote(ids, service_scope=s.scope)
            legacy_total = _q(sum((item.sell_amount for item in result.line_items), Decimal("0")))
            reason = (
                "Production COLLECT uses native AUD tariffs where they exist and otherwise margin then "
                "PGK / (TT SELL x (1 + CAF)); the locked rule is PGK SELL / TT BUY x 1.10 with no margin. "
                "Not reconciled; wiring is a separate gate."
            )
        except Exception as exc:
            legacy_total = None
            reason = f"Production COLLECT AUD could not be priced ({type(exc).__name__}: {exc}). Not reconciled."
        self._emit(s, "TOTAL", "production_collect_total_sell", NOT_COMPARABLE, legacy_total,
                   approved.totals["total_sell"], "AUD", "production engine vs locked export rule", reason)


def _totals(lines: dict[str, Line]) -> dict[str, Decimal]:
    zero = Decimal("0.00")
    return {
        "total_sell": sum((l.sell_amount for l in lines.values()), zero),
        "total_gst": sum((l.gst_amount for l in lines.values()), zero),
        "total_sell_incl_gst": sum((l.sell_incl_gst for l in lines.values()), zero),
        "total_cost_pgk": sum((l.cost_amount for l in lines.values()), zero),
    }


def run_export_shadow(
    *,
    quote_date: date,
    lanes=DEFAULT_LANES,
    weights=DEFAULT_WEIGHTS,
    scopes=DEFAULT_SCOPES,
    currencies=DEFAULT_CURRENCIES,
    using: str = "default",
) -> ExportShadowReport:
    with read_only_database(using):
        return _ExportShadow(quote_date, lanes, weights, scopes, currencies, using).run()
