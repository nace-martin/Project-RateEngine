"""Stage-2 read-only commercial shadow pricing (Pilot Gate B3K).

Compares, for Pilot imports, the quote the **production import engine** produces
from legacy rate rows with the quote the **same engine** produces when its rate
lookups return Rate Matrix tariffs. Everything downstream of the rate lookup is
the unmodified production code: FX, CAF, margin, GST classification, minimum and
maximum charges, tier selection, and percentage-surcharge relationships. No
commercial formula is re-implemented here.

Safety:

- Diagnostic only. Not imported by any quote, engine, adapter, or dispatcher.
- Runs in a read-only, rolled-back transaction. Nothing is written or mutated.
- Does not invent or approve CAF, margin, GST, FX, or any commercial policy. The
  values read from ``CommercialTermsPolicy`` and ``FxMarketRate`` are *legacy
  observed policy* and are reported with provenance. They are **not approved as
  Rate Matrix or cutover authority**.
- Fails closed: missing or ambiguous policy, missing / ambiguous / stale FX, an
  ambiguous or invalid resolver result, a percentage-basis or GST-treatment
  disagreement all produce ``BLOCKED`` for the scenario. No default is filled in.

Classifications: MATCH, EXPECTED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, BLOCKED,
NOT_COMPARABLE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from django.db.models import Q

from core.charge_rules import CALCULATION_LOOKUP_RATE, RuleEvaluation
from core.geo_models import GeoLocationIdentifier
from pricing_v4.category_rules import is_local_rate_category
from pricing_v4.commercial_models import CommercialProductCode, CommercialTermsPolicy
from pricing_v4.engine.import_engine import (
    ImportPricingEngine,
    PaymentTerm,
    ServiceScope,
)
from pricing_v4.services import rate_matrix_resolver as resolver
from pricing_v4.services.fx_resolver import FxResolutionError, resolve_market_fx_pair
from pricing_v4.services.rate_matrix_manifest import read_only_database
from pricing_v4.services.rate_matrix_shadow import run_shadow
from quotes.currency_rules import determine_quote_currency

MATCH = "MATCH"
EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"
BLOCKED = "BLOCKED"
NOT_COMPARABLE = "NOT_COMPARABLE"
CLASSIFICATIONS = (MATCH, EXPECTED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, BLOCKED, NOT_COMPARABLE)

DEFAULT_LANES = (("BNE", "POM"), ("SYD", "POM"))
DEFAULT_WEIGHTS = tuple(Decimal(w) for w in ("30", "45", "100", "250", "500", "999", "1000", "1001"))
DEFAULT_TERMS = ("COLLECT", "PREPAID")
DEFAULT_SCOPES = ("A2D", "D2D")
NOT_APPROVED = "LEGACY OBSERVED POLICY. NOT APPROVED FOR CUTOVER."
GST_SOURCE = "quotes.tax_policy.PNG_GST_RATE_DECIMAL (code constant) via get_png_gst_category"


class ShadowBlocked(Exception):
    """A scenario cannot be priced without inventing a value. Carries a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Line:
    product_code: str
    leg: str
    sell_amount: Decimal
    sell_currency: str
    cost_amount: Decimal
    cost_currency: str
    gst_amount: Decimal
    gst_category: str
    sell_incl_gst: Decimal
    fx_applied: bool
    caf_applied: bool
    margin_applied: bool
    is_rate_missing: bool = False

    def stage(self, aspect: str) -> str:
        if aspect == "gst_amount" or aspect == "sell_incl_gst":
            return f"GST classification ({self.gst_category or 'none'}) on the sell amount"
        steps = ["rate lookup"]
        if self.fx_applied:
            steps.append("FX")
        if self.caf_applied:
            steps.append("CAF")
        if self.margin_applied:
            steps.append("margin")
        return " -> ".join(steps) + (" (explicit SELL tariff)" if self.leg == "DESTINATION" else " (cost-plus)")


@dataclass
class Priced:
    lines: dict[str, Line]
    totals: dict[str, Decimal]


@dataclass
class Scenario:
    lane: str
    weight: Decimal
    term: str
    scope: str
    quote_currency: str

    @property
    def key(self) -> str:
        return f"{self.weight.normalize():f}kg|{self.term}|{self.scope}|{self.quote_currency}"


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
    stage: str = ""
    provenance: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Stage2Report:
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
            "mode": "SHADOW_STAGE_2", "writes_performed": 0, "quote_date": self.quote_date.isoformat(),
            "counts": self.counts(), "policy_provenance": self.policy, "fx_provenance": self.fx_provenance,
            "notes": self.notes, "records": [r.as_dict() for r in self.records],
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True, default=str)

    def render_text(self, *, show_matches: bool = False) -> str:
        counts = self.counts()
        out = [
            "Rate Matrix Stage-2 commercial shadow pricing (diagnostic only; no quote is affected)",
            f"Quote date: {self.quote_date.isoformat()}",
            "   ".join(f"{name} {counts[name]}" for name in CLASSIFICATIONS),
        ]
        if self.policy:
            out.append(f"Policy ({NOT_APPROVED}): {json.dumps(self.policy, sort_keys=True, default=str)}")
        else:
            out.append("Policy: none resolved")
        for note in self.notes:
            out.append(f"Note: {note}")
        for r in self.records:
            if r.classification == MATCH and not show_matches:
                continue
            out.append(
                f"  {r.classification:22s} {r.lane} [{r.scenario}] {r.product_code} {r.aspect}: "
                f"legacy={r.legacy} shadow={r.shadow} {r.currency}"
            )
            for label, value in (("stage", r.stage), ("provenance", r.provenance), ("reason", r.reason)):
                if value:
                    out.append(f"      {label}: {value}")
        out += ["", "Writes performed: 0"]
        return "\n".join(out)


# ----------------------------------------------------------------------------- Rate Matrix records


@dataclass
class ShadowRate:
    """A Rate Matrix tariff shaped like the legacy rate records the production engine reads."""

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
    provenance: dict[str, Any] = field(default_factory=dict)


def _shadow_rate(tariff: resolver.ResolvedTariff, *, supplier: str | None) -> ShadowRate:
    rate = ShadowRate(
        currency=tariff.currency_code, min_charge=tariff.min_charge, max_charge=tariff.max_charge,
        agent=SimpleNamespace(name=supplier) if supplier else None,
        provenance={"sheet": tariff.sheet_name, "version": tariff.sheet_version, "line_id": str(tariff.line_id)},
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
        raise ShadowBlocked("UNSUPPORTED_BASIS", f"Rate basis {basis} is not supported by the shadow.")
    return rate


class _MatrixLookup:
    """Resolves Rate Matrix tariffs for one scenario and fails closed on anything not exact."""

    def __init__(self, scenario: Scenario, origin: str, destination: str, quote_date: date, using: str):
        self.s, self.origin, self.destination = scenario, origin, destination
        self.quote_date, self.using = quote_date, using
        self._cache: dict[tuple[str, str], ShadowRate | None] = {}
        self._supplier: tuple[Any, str] | None = None

    def _supplier_for_lane(self):
        if self._supplier is None:
            from pricing_v4.rate_matrix_models import RateLine

            carriers = {
                (line.sheet.carrier_id, line.sheet.carrier.legal_name)
                for line in RateLine.objects.using(self.using).filter(
                    Q(applicability__origin__identifiers__code=self.origin,
                      applicability__origin__identifiers__scheme=GeoLocationIdentifier.Scheme.IATA),
                    sheet__is_active=True, sheet__rate_type=resolver.BUY, sheet__valid_from__lte=self.quote_date,
                ).filter(Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=self.quote_date))
                .select_related("sheet", "sheet__carrier")
                if line.sheet.carrier_id
            }
            if len(carriers) != 1:
                raise ShadowBlocked(
                    "SUPPLIER_NOT_SINGLE",
                    f"Rate Matrix BUY sheets for {self.origin} name {len(carriers)} suppliers; exactly one is required.",
                )
            self._supplier = next(iter(carriers))
        return self._supplier

    def _check(self, pc, tariff: resolver.ResolvedTariff) -> None:
        mirror = CommercialProductCode.objects.using(self.using).filter(code=pc.code).first()
        if mirror is not None and mirror.gst_treatment != pc.gst_treatment:
            raise ShadowBlocked(
                "GST_TREATMENT_MISMATCH",
                f"{pc.code}: CommercialProductCode GST treatment '{mirror.gst_treatment}' differs from the "
                f"legacy ProductCode '{pc.gst_treatment}'.",
            )
        if tariff.rate_basis == "PERCENTAGE":
            legacy_base = pc.percent_of_product_code.code if pc.percent_of_product_code_id else None
            if tariff.percentage_basis_product_code != legacy_base:
                raise ShadowBlocked(
                    "PERCENTAGE_BASIS_MISMATCH",
                    f"{pc.code}: Rate Matrix percentage basis '{tariff.percentage_basis_product_code}' differs "
                    f"from the legacy basis '{legacy_base}'.",
                )

    def _resolve(self, pc, context: resolver.ResolutionContext, supplier: str | None) -> ShadowRate | None:
        result = resolver.resolve(context, using=self.using)
        if result.outcome == resolver.NO_MATCH:
            return None
        if result.outcome != resolver.EXACT_MATCH:
            raise ShadowBlocked(
                f"RESOLVER_{result.outcome}", f"{pc.code}: {result.outcome}: {'; '.join(result.reasons)}"
            )
        self._check(pc, result.tariff)
        return _shadow_rate(result.tariff, supplier=supplier)

    def buy(self, pc) -> ShadowRate | None:
        key = ("BUY", pc.code)
        if key not in self._cache:
            supplier_id, supplier_name = self._supplier_for_lane()
            self._cache[key] = self._resolve(pc, resolver.ResolutionContext(
                rate_type=resolver.BUY, direction="IMPORT", effective_date=self.quote_date, product_code=pc.code,
                origin_iata=self.origin, destination_iata=self.destination, supplier_id=supplier_id,
                chargeable_weight=self.s.weight,
            ), supplier_name)
        return self._cache[key]

    def sell(self, pc) -> ShadowRate | None:
        key = ("SELL", pc.code)
        if key not in self._cache:
            self._cache[key] = self._resolve(pc, resolver.ResolutionContext(
                rate_type=resolver.SELL, direction="IMPORT", effective_date=self.quote_date, product_code=pc.code,
                origin_iata=self.origin, destination_iata=self.destination, payment_term=self.s.term,
                quote_currency=self.s.quote_currency, chargeable_weight=self.s.weight,
            ), None)
        return self._cache[key]


class MatrixShadowImportEngine(ImportPricingEngine):
    """The production import engine with only its four rate lookups redirected to the Rate Matrix."""

    def __init__(self, *, matrix: _MatrixLookup, **kwargs):
        super().__init__(**kwargs)
        self._matrix = matrix

    def _get_cogs(self, pc, leg=None):
        if leg == "DESTINATION" and is_local_rate_category(pc.category):
            return None  # The Rate Matrix holds no destination BUY tariff.
        return self._matrix.buy(pc)

    def _get_local_cogs(self, pc, leg):
        return None

    def _get_sell_rate(self, pc, leg):
        return None  # Origin and freight sell is cost-plus, as in legacy (no import sell rows).

    def _get_destination_sell_rate(self, pc):
        return self._matrix.sell(pc)

    def _calculate_cogs_amount(self, cogs, pc) -> RuleEvaluation:
        # The production first pass reads legacy rows to seed the surcharge-basis cache. Ignore the
        # legacy record and use the Rate Matrix so no legacy value leaks into the shadow.
        record = cogs if isinstance(cogs, ShadowRate) else self._matrix.buy(pc)
        if record is None:
            return RuleEvaluation(CALCULATION_LOOKUP_RATE, Decimal("0.00"))
        return super()._calculate_cogs_amount(record, pc)


# ----------------------------------------------------------------------------- orchestration


def run_stage2(
    *,
    quote_date: date,
    lanes=DEFAULT_LANES,
    weights=DEFAULT_WEIGHTS,
    terms=DEFAULT_TERMS,
    scopes=DEFAULT_SCOPES,
    stage1_registry: list[dict[str, str]] | None = None,
    max_fx_age_days: int | None = None,
    using: str = "default",
) -> Stage2Report:
    with read_only_database(using):
        return _Stage2(quote_date, lanes, weights, terms, scopes, stage1_registry or [], max_fx_age_days, using).run()


class _Stage2:
    def __init__(self, quote_date, lanes, weights, terms, scopes, registry, max_fx_age_days, using):
        self.quote_date, self.lanes, self.weights = quote_date, tuple(lanes), tuple(weights)
        self.terms, self.scopes, self.registry = tuple(terms), tuple(scopes), registry
        self.max_fx_age_days, self.using = max_fx_age_days, using
        self.report = Stage2Report(quote_date=quote_date)
        self._fx_seen: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------------- policy

    def _policy(self):
        matches = list(
            CommercialTermsPolicy.objects.using(self.using)
            .filter(is_active=True, valid_from__lte=self.quote_date)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=self.quote_date))
            .order_by("-valid_from", "policy_code")
        )
        if not matches:
            raise ShadowBlocked("POLICY_MISSING", f"No active CommercialTermsPolicy on {self.quote_date}.")
        if len(matches) > 1:
            raise ShadowBlocked(
                "POLICY_AMBIGUOUS",
                f"{len(matches)} active CommercialTermsPolicy rows cover {self.quote_date}: "
                f"{', '.join(p.policy_code for p in matches)}. Production would silently take the newest; "
                "the shadow does not.",
            )
        policy = matches[0]
        for name in ("import_caf_rate", "margin_rate"):
            if getattr(policy, name) is None:
                raise ShadowBlocked("POLICY_INCOMPLETE", f"Policy {policy.policy_code} has no {name}.")
        self.report.policy = {
            "status": NOT_APPROVED, "table": "policy_commercial_terms", "policy_code": policy.policy_code,
            "valid_from": policy.valid_from.isoformat(),
            "valid_until": policy.valid_until.isoformat() if policy.valid_until else None,
            "import_caf_percent": str(policy.import_caf_percent), "margin_percent": str(policy.margin_percent),
            "margin_method": policy.margin_method, "gst_standard_percent_observed": str(policy.gst_standard_percent),
            "gst_rate_used_by_engine": GST_SOURCE,
        }
        return policy

    # ---------------------------------------------------------------- run

    def run(self) -> Stage2Report:
        try:
            policy = self._policy()
        except ShadowBlocked as blocked:
            policy = None
            self._block_all(blocked)
        if policy is not None:
            for origin, destination in self.lanes:
                self._lane(origin, destination, policy)
        return self.report

    def _block_all(self, blocked: ShadowBlocked) -> None:
        for origin, destination in self.lanes:
            for scenario in self._scenarios(origin, destination):
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{blocked.code}: {blocked.message}")

    def _country(self, iata: str) -> str:
        identifier = (
            GeoLocationIdentifier.objects.using(self.using)
            .filter(scheme=GeoLocationIdentifier.Scheme.IATA, code=iata).select_related("location").first()
        )
        return (identifier.location.country_code or "").upper() if identifier else ""

    def _scenarios(self, origin: str, destination: str) -> list[Scenario]:
        out = []
        for weight in self.weights:
            for term in self.terms:
                currency = determine_quote_currency(
                    "IMPORT", term, self._country(origin), self._country(destination)
                )
                for scope in self.scopes:
                    out.append(Scenario(f"{origin}-{destination}", weight, term, scope, currency))
        return out

    def _lane(self, origin: str, destination: str, policy) -> None:
        stage1 = self._stage1_index(origin, destination)
        for scenario in self._scenarios(origin, destination):
            try:
                legacy = self._price(ImportPricingEngine, scenario, origin, destination, policy)
                shadow = self._price(MatrixShadowImportEngine, scenario, origin, destination, policy, matrix=True)
            except ShadowBlocked as blocked:
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{blocked.code}: {blocked.message}")
                continue
            except FxResolutionError as exc:
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{type(exc).__name__}: {exc}")
                continue
            try:
                self._fx_checks(scenario, legacy, shadow)
            except ShadowBlocked as blocked:
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{blocked.code}: {blocked.message}")
                continue
            except FxResolutionError as exc:
                self._emit(scenario, "-", "scenario", BLOCKED, reason=f"{type(exc).__name__}: {exc}")
                continue
            self._compare(scenario, legacy, shadow, stage1, destination)

    def _price(self, engine_class, scenario: Scenario, origin, destination, policy, *, matrix: bool = False) -> Priced:
        quote_currency = scenario.quote_currency
        tt_buy = tt_sell = None
        if quote_currency != "PGK":  # Same pre-resolution as the production adapter.
            pair = resolve_market_fx_pair(quote_currency, "PGK", self.quote_date)
            tt_buy, tt_sell = pair.tt_buy, pair.tt_sell
        kwargs = {
            "quote_date": self.quote_date, "origin": origin, "destination": destination,
            "chargeable_weight_kg": scenario.weight, "payment_term": PaymentTerm(scenario.term),
            "service_scope": ServiceScope(scenario.scope), "tt_buy": tt_buy, "tt_sell": tt_sell,
            "caf_rate": policy.import_caf_rate, "margin_rate": policy.margin_rate, "margin_method": policy.margin_method,
            "quote_currency": quote_currency,
        }
        if matrix:
            kwargs["matrix"] = _MatrixLookup(scenario, origin, destination, self.quote_date, self.using)
        result = engine_class(**kwargs).calculate_quote()
        lines = {}
        for item in result.line_items:
            lines[item.product_code] = Line(
                product_code=item.product_code, leg=item.leg, sell_amount=item.sell_amount,
                sell_currency=item.sell_currency, cost_amount=item.cost_amount, cost_currency=item.cost_currency,
                gst_amount=item.gst_amount, gst_category=item.gst_category, sell_incl_gst=item.sell_incl_gst,
                fx_applied=item.fx_applied, caf_applied=item.caf_applied, margin_applied=item.margin_applied,
                is_rate_missing=bool(getattr(item, "is_rate_missing", False)),
            )
        totals = {
            "total_sell_pgk": result.total_sell_pgk, "total_gst": result.total_gst,
            "total_sell_incl_gst": result.total_sell_incl_gst, "total_cost_pgk": result.total_cost_pgk,
            "total_margin": result.total_margin,
        }
        return Priced(lines, totals)

    def _fx_checks(self, scenario: Scenario, *priced: Priced) -> None:
        # Only currencies that took part in a conversion. A zero cost carries the engine's placeholder
        # currency and converts to zero without any rate.
        currencies = set()
        for p in priced:
            for line in p.lines.values():
                if line.sell_currency and line.sell_currency != "PGK":
                    currencies.add(line.sell_currency)
                if line.cost_amount != 0 and line.cost_currency and line.cost_currency != "PGK":
                    currencies.add(line.cost_currency)
        for currency in sorted(currencies):
            pair = resolve_market_fx_pair(currency, "PGK", self.quote_date)
            age = (self.quote_date - pair.effective_date).days
            info = {
                "pair": f"{currency}/PGK", "source": pair.source, "effective_date": pair.effective_date.isoformat(),
                "tt_buy": str(pair.tt_buy), "tt_sell": str(pair.tt_sell), "age_days": age,
                "status": NOT_APPROVED,
            }
            self._fx_seen[info["pair"]] = info
            self.report.fx_provenance = sorted(self._fx_seen.values(), key=lambda i: i["pair"])
            if self.max_fx_age_days is not None and age > self.max_fx_age_days:
                raise ShadowBlocked(
                    "FX_STALE",
                    f"{currency}/PGK rate is {age} days old (limit {self.max_fx_age_days}); effective "
                    f"{pair.effective_date.isoformat()} from {pair.source}.",
                )

    # ---------------------------------------------------------------- Stage-1 explanation lookup

    def _stage1_index(self, origin: str, destination: str) -> dict[tuple[str, str, str], dict[str, Any]]:
        """For each (side, product, context) whether Stage-1 native differences are explained."""
        stage1 = run_shadow(
            quote_date=self.quote_date, lanes=((origin, destination),), registry=self.registry,
            weights=(Decimal(100),), using=self.using, read_only=False,
        )
        index: dict[tuple[str, str, str], dict[str, Any]] = {}
        for record in stage1.records:
            if record.classification == "MATCH":
                continue
            key = (record.side, record.product_code, record.context)
            entry = index.setdefault(key, {"explained": [], "unexplained": []})
            (entry["explained"] if record.evidence else entry["unexplained"]).append(record.aspect)
        return index

    # ---------------------------------------------------------------- compare

    def _emit(self, scenario, product_code, aspect, classification, legacy=None, shadow=None, currency="",
              stage="", reason=""):
        provenance = ""
        if self.report.policy:
            provenance = f"policy {self.report.policy['policy_code']} ({NOT_APPROVED})"
        if self._fx_seen:
            provenance += "; FX " + ", ".join(
                f"{i['pair']} {i['source']} {i['effective_date']}" for i in self._fx_seen.values()
            )
        self.report.records.append(Record(
            scenario.lane, scenario.key, product_code, aspect, classification,
            None if legacy is None else str(legacy), None if shadow is None else str(shadow), currency, stage,
            provenance.strip("; "), reason,
        ))

    def _compare(self, s: Scenario, legacy: Priced, shadow: Priced, stage1, destination: str) -> None:
        differing_unexplained = False
        any_difference = False
        for code in sorted(set(legacy.lines) | set(shadow.lines)):
            left, right = legacy.lines.get(code), shadow.lines.get(code)
            leg = (left or right).leg
            side = "SELL" if leg == "DESTINATION" else "BUY"
            context = f"{s.term}/{s.quote_currency}" if side == "SELL" else ""
            lane_key = (side, code, context)
            s1 = stage1.get(lane_key, {"explained": [], "unexplained": []})

            if left is None or right is None:
                present = right if left is None else left
                any_difference = True
                cls, reason = self._explain(s1, f"charge present only in {'Rate Matrix shadow' if left is None else 'legacy'}")
                differing_unexplained |= cls == UNEXPLAINED_DIFFERENCE
                self._emit(s, code, "presence", cls, "absent" if left is None else "present",
                           "present" if left is None else "absent", present.sell_currency,
                           f"charge {'added' if left is None else 'dropped'} before pricing", reason)
                continue

            for aspect in ("sell_amount", "gst_amount", "sell_incl_gst"):
                a, b = getattr(left, aspect), getattr(right, aspect)
                currency = left.sell_currency
                stage = left.stage(aspect)
                if a == b:
                    self._emit(s, code, aspect, MATCH, a, b, currency, stage)
                    continue
                any_difference = True
                cls, reason = self._explain(s1, f"{aspect} differs")
                differing_unexplained |= cls == UNEXPLAINED_DIFFERENCE
                self._emit(s, code, aspect, cls, a, b, currency, stage, reason)
            if left.cost_amount == right.cost_amount != 0 and left.cost_currency == right.cost_currency:
                self._emit(s, code, "cost_amount", MATCH, left.cost_amount, right.cost_amount,
                           left.cost_currency, "BUY rate lookup (native currency, before FX)")
            elif (left.cost_amount, right.cost_amount) != (0, 0) and (
                left.cost_amount != right.cost_amount or left.cost_currency != right.cost_currency
            ):
                if leg == "DESTINATION" and right.cost_amount == 0:
                    self._emit(s, code, "cost_amount", NOT_COMPARABLE, left.cost_amount, right.cost_amount,
                               left.cost_currency, "BUY lookup",
                               "The Rate Matrix holds no destination BUY tariff, so cost is not comparable.")
                else:
                    any_difference = True
                    cls, reason = self._explain(s1, "cost_amount differs")
                    differing_unexplained |= cls == UNEXPLAINED_DIFFERENCE
                    self._emit(s, code, "cost_amount", cls, left.cost_amount, right.cost_amount,
                               left.cost_currency, left.stage("sell_amount").split(" -> ")[0], reason)

        cost_not_comparable = any(
            r.classification == NOT_COMPARABLE and r.aspect == "cost_amount" and r.scenario == s.key
            and r.lane == s.lane for r in self.report.records
        )
        for name in ("total_sell_pgk", "total_gst", "total_sell_incl_gst", "total_cost_pgk", "total_margin"):
            a, b = legacy.totals[name], shadow.totals[name]
            if name in ("total_cost_pgk", "total_margin") and cost_not_comparable and a != b:
                self._emit(s, "TOTAL", name, NOT_COMPARABLE, a, b, "PGK", "totals",
                           "Includes destination cost that the Rate Matrix does not hold.")
            elif a == b:
                self._emit(s, "TOTAL", name, MATCH, a, b, "PGK", "totals")
            else:
                cls = UNEXPLAINED_DIFFERENCE if differing_unexplained or not any_difference else EXPECTED_DIFFERENCE
                reason = (
                    "Follows the explained line differences above." if cls == EXPECTED_DIFFERENCE
                    else "No explained line difference accounts for this total."
                )
                self._emit(s, "TOTAL", name, cls, a, b, "PGK", "totals", reason)

    @staticmethod
    def _explain(stage1: dict[str, Any], what: str) -> tuple[str, str]:
        if stage1["explained"] and not stage1["unexplained"]:
            return EXPECTED_DIFFERENCE, (
                f"{what}; Stage-1 native differences explained in the registry: {', '.join(sorted(set(stage1['explained'])))}."
            )
        if stage1["unexplained"]:
            return UNEXPLAINED_DIFFERENCE, f"{what}; Stage-1 unexplained native differences: {', '.join(sorted(set(stage1['unexplained'])))}."
        return UNEXPLAINED_DIFFERENCE, f"{what}; Stage-1 native facts match, so the divergence arises in the downstream calculation."
