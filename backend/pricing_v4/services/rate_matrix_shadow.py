"""Stage-1 read-only shadow comparison: Rate Matrix versus legacy rate rows (Pilot Gate B3J).

Compares **native tariff facts only**: charge identity and presence, currency, rate
basis, rate, minimum, maximum, additive flat amount, percentage and its basis,
tier tables, selected rate at stated weights, applicability, and validity.

It never converts currency and never computes CAF, margin, GST, or a quote total.
It is not called by any quote, engine, adapter, or dispatcher, and it writes
nothing: the run happens inside a read-only, rolled-back transaction.

Legacy facts are read through the production selectors in ``rate_selector`` so
the comparison reflects what live pricing would pick, not a re-implemented
lookup. Differences are never normalised away. A value difference is
``UNEXPLAINED_DIFFERENCE`` unless an operator-supplied *explained differences*
registry names that exact difference (same lane, side, charge, aspect, and the
same legacy and matrix values) with a reason and evidence. A registry entry that
no longer matches anything is reported as stale.

Classifications: MATCH, EXPECTED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, LEGACY_ONLY,
RATE_MATRIX_ONLY, NOT_COMPARABLE.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q

from core.geo_models import GeoLocationIdentifier
from pricing_v4.models import ImportCOGS, LocalSellRate, ProductCode
from pricing_v4.rate_matrix_models import RateLine
from pricing_v4.services import rate_matrix_resolver as resolver
from pricing_v4.services.rate_matrix_manifest import (
    ManifestParseError,
    parse_manifest_text,
    read_only_database,
)
from pricing_v4.services.rate_selector import (
    RateAmbiguityError,
    RateNotFoundError,
    RateSelectionContext,
    select_import_cogs_rate,
    select_local_sell_rate,
)
from quotes.currency_rules import determine_quote_currency

MATCH = "MATCH"
EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"
LEGACY_ONLY = "LEGACY_ONLY"
RATE_MATRIX_ONLY = "RATE_MATRIX_ONLY"
NOT_COMPARABLE = "NOT_COMPARABLE"
CLASSIFICATIONS = (
    MATCH, EXPECTED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, LEGACY_ONLY, RATE_MATRIX_ONLY, NOT_COMPARABLE,
)

DEFAULT_LANES = (("BNE", "POM"), ("SYD", "POM"))
DEFAULT_WEIGHTS = tuple(Decimal(w) for w in ("1", "30", "44", "45", "46", "99", "100", "249", "250", "499", "500", "999", "1000", "1001", "1500"))
VALUE_ASPECTS = (
    "currency", "unit_rate", "additive_flat_amount", "min_charge", "max_charge", "percentage_rate",
    "percentage_basis", "tiers",
)
# Rate values whose meaning depends on the basis. Currency and the minimum/maximum charge are
# comparable whatever the basis is.
BASIS_DEPENDENT_ASPECTS = ("unit_rate", "additive_flat_amount", "percentage_rate", "percentage_basis", "tiers")
REGISTRY_KEYS = ("lane", "side", "product_code", "aspect", "legacy", "matrix", "reason", "evidence")
PAYMENT_TERMS = ("COLLECT", "PREPAID")
EMPTY_TIERS = "(none)"


@dataclass(frozen=True)
class Facts:
    """Native facts of one side, rendered as strings so both sides compare exactly."""

    currency: str | None = None
    basis: str | None = None
    unit_rate: str | None = None
    additive_flat_amount: str | None = None
    min_charge: str | None = None
    max_charge: str | None = None
    percentage_rate: str | None = None
    percentage_basis: str | None = None
    tiers: tuple[tuple[str, str], ...] = ()
    validity: str | None = None
    origin: str | None = None
    destination: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class Record:
    lane: str
    side: str
    product_code: str
    aspect: str
    classification: str
    legacy: str | None = None
    matrix: str | None = None
    context: str = ""
    reason: str = ""
    evidence: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane, "side": self.side, "product_code": self.product_code, "context": self.context,
            "aspect": self.aspect, "classification": self.classification, "legacy": self.legacy,
            "matrix": self.matrix, "reason": self.reason, "evidence": self.evidence,
        }


@dataclass
class ShadowReport:
    quote_date: date
    weights: tuple[Decimal, ...]
    records: list[Record] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stale_registry_entries: list[dict[str, Any]] = field(default_factory=list)
    registry_errors: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        found = Counter(record.classification for record in self.records)
        return {name: found.get(name, 0) for name in CLASSIFICATIONS}

    @property
    def unexplained(self) -> list[Record]:
        return [r for r in self.records if r.classification == UNEXPLAINED_DIFFERENCE]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "SHADOW_STAGE_1", "writes_performed": 0, "quote_date": self.quote_date.isoformat(),
            "weights": [str(w) for w in self.weights], "counts": self.counts(),
            "records": [record.as_dict() for record in self.records], "provenance": self.provenance,
            "notes": self.notes, "stale_registry_entries": self.stale_registry_entries,
            "registry_errors": self.registry_errors,
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def render_text(self, *, show_matches: bool = False) -> str:
        counts = self.counts()
        out = [
            "Rate Matrix Stage-1 shadow comparison (native facts only; no FX, CAF, margin, GST, or totals)",
            f"Quote date: {self.quote_date.isoformat()}   Weights: {', '.join(str(w) for w in self.weights)}",
            "Mode: READ ONLY (no rows are written; no quote is affected)",
            "",
            "   ".join(f"{name} {counts[name]}" for name in CLASSIFICATIONS),
        ]
        for note in self.notes:
            out.append(f"Note: {note}")
        for record in self.records:
            if record.classification == MATCH and not show_matches:
                continue
            ctx = f" [{record.context}]" if record.context else ""
            out.append(
                f"  {record.classification:23s} {record.lane} {record.side} {record.product_code}{ctx} "
                f"{record.aspect}: legacy={record.legacy} matrix={record.matrix}"
            )
            if record.reason:
                out.append(f"      reason: {record.reason}")
            if record.evidence:
                out.append(f"      evidence: {record.evidence}")
        if self.stale_registry_entries:
            out += ["", f"Stale explained-difference entries ({len(self.stale_registry_entries)}):"]
            out += [f"  {json.dumps(entry, sort_keys=True)}" for entry in self.stale_registry_entries]
        for error in self.registry_errors:
            out.append(f"Registry error: {error}")
        out += ["", "Writes performed: 0"]
        return "\n".join(out)


# ----------------------------------------------------------------------------- registry


def load_registry(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse an explained-differences registry. Strict; returns (entries, errors)."""
    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        return [], [f"Registry is not strict JSON: {exc}"]
    if not isinstance(data, dict) or set(data) != {"registry_version", "entries"} or data["registry_version"] != 1:
        return [], ["Registry must be an object with exactly registry_version 1 and entries."]
    if not isinstance(data["entries"], list):
        return [], ["Registry entries must be an array."]
    entries, errors = [], []
    for index, entry in enumerate(data["entries"]):
        ok = isinstance(entry, dict) and set(entry) == set(REGISTRY_KEYS) and all(
            isinstance(entry[key], str) and entry[key].strip() == entry[key] and entry[key] for key in REGISTRY_KEYS
        ) if isinstance(entry, dict) and set(entry) == set(REGISTRY_KEYS) else False
        if ok:
            entries.append(entry)
        else:
            errors.append(f"entries[{index}] must have exactly {', '.join(REGISTRY_KEYS)} as non-blank strings.")
    return entries, errors


# ----------------------------------------------------------------------------- entry point


def run_shadow(
    *,
    quote_date: date,
    lanes=DEFAULT_LANES,
    weights=DEFAULT_WEIGHTS,
    registry: list[dict[str, str]] | None = None,
    registry_errors: list[str] | None = None,
    legacy_agent_code: str | None = None,
    using: str = "default",
    read_only: bool = True,
) -> ShadowReport:
    """Run the comparison inside a read-only, rolled-back transaction.

    ``read_only=False`` is for a caller that is already inside ``read_only_database`` (the Stage-2
    shadow): the nested block would otherwise switch the connection back to writable on exit.
    """
    shadow = _Shadow(quote_date, tuple(lanes), tuple(weights), registry or [], legacy_agent_code, using)
    if not read_only:
        return shadow.run(registry_errors or [])
    with read_only_database(using):
        return shadow.run(registry_errors or [])


def _fmt(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def _validity(start: date | None, end: date | None) -> str:
    return f"{start.isoformat() if start else 'open'}..{end.isoformat() if end else 'open'}"


class _Shadow:
    def __init__(self, quote_date, lanes, weights, registry, legacy_agent_code, using):
        self.quote_date = quote_date
        self.lanes = lanes
        self.weights = weights
        self.registry = registry
        self.used: set[int] = set()
        self.using = using
        self.report = ShadowReport(quote_date=quote_date, weights=weights)
        self.agent_id = None
        if legacy_agent_code:
            from pricing_v4.models import Agent

            agent = Agent.objects.using(using).filter(code=legacy_agent_code).first()
            self.agent_id = agent.id if agent else None
            if agent is None:
                self.report.notes.append(f"Legacy agent code '{legacy_agent_code}' not found; no agent filter applied.")
        self._product_ids: dict[str, int] = {}

    # ---------------------------------------------------------------- orchestration

    def run(self, registry_errors: list[str]) -> ShadowReport:
        self.report.registry_errors = list(registry_errors)
        for origin, destination in self.lanes:
            self._buy_lane(origin, destination)
        for destination in sorted({destination for _origin, destination in self.lanes}):
            self._sell_destination(destination)
        for index, entry in enumerate(self.registry):
            if index not in self.used:
                self.report.stale_registry_entries.append(entry)
        self.report.notes.append(
            "Legacy import SELL for origin and freight charges is cost-plus (no import sell rows); only BUY "
            "facts exist for those charges. Destination SELL is compared to LocalSellRate."
        )
        return self.report

    # ---------------------------------------------------------------- helpers

    def _product_id(self, code: str) -> int | None:
        if code not in self._product_ids:
            found = ProductCode.objects.using(self.using).filter(code=code).values_list("id", flat=True).first()
            self._product_ids[code] = found
        return self._product_ids[code]

    def _location(self, iata: str):
        identifier = (
            GeoLocationIdentifier.objects.using(self.using)
            .filter(scheme=GeoLocationIdentifier.Scheme.IATA, code=iata).select_related("location").first()
        )
        return identifier.location if identifier else None

    def _emit(self, lane, side, code, aspect, classification, legacy=None, matrix=None, context="", reason=""):
        evidence = ""
        if classification != MATCH:
            for index, entry in enumerate(self.registry):
                if (
                    entry["lane"] in (lane, "*") and entry["side"] == side and entry["product_code"] == code
                    and entry["aspect"] == aspect and entry["legacy"] == str(legacy) and entry["matrix"] == str(matrix)
                ):
                    self.used.add(index)
                    reason, evidence = entry["reason"], entry["evidence"]
                    if classification == UNEXPLAINED_DIFFERENCE:
                        classification = EXPECTED_DIFFERENCE
                    break
        self.report.records.append(
            Record(lane, side, code, aspect, classification, None if legacy is None else str(legacy),
                   None if matrix is None else str(matrix), context, reason, evidence)
        )

    # ---------------------------------------------------------------- BUY (ImportCOGS)

    def _buy_lane(self, origin: str, destination: str) -> None:
        lane = f"{origin}-{destination}"
        origin_location, destination_location = self._location(origin), self._location(destination)
        if origin_location is None or destination_location is None:
            self.report.notes.append(f"{lane}: an IATA code does not resolve; lane not comparable.")
            return

        matrix_lines = list(
            RateLine.objects.using(self.using)
            .filter(
                Q(applicability__origin=origin_location)
                & (Q(applicability__destination__isnull=True) | Q(applicability__destination=destination_location)),
                sheet__is_active=True, sheet__rate_type=resolver.BUY, sheet__valid_from__lte=self.quote_date,
            )
            .filter(Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=self.quote_date))
            .select_related("sheet", "product_code")
        )
        suppliers = {line.sheet.carrier_id for line in matrix_lines}
        matrix_codes = {line.product_code.code for line in matrix_lines}
        legacy_rows = list(
            ImportCOGS.objects.using(self.using)
            .filter(origin_airport=origin, valid_from__lte=self.quote_date, valid_until__gte=self.quote_date)
            .filter(Q(destination_airport=destination) | Q(destination_airport__isnull=True) | Q(destination_airport=""))
            .select_related("product_code", "product_code__percent_of_product_code")
        )
        legacy_scopes = {row.product_code.code: row.scope for row in legacy_rows}
        codes = sorted(matrix_codes | set(legacy_scopes))
        supplier_id = next(iter(suppliers)) if len(suppliers) == 1 and None not in suppliers else None
        if matrix_codes and supplier_id is None:
            self.report.notes.append(f"{lane}: BUY lines do not name exactly one supplier; Rate Matrix side not comparable.")

        for code in codes:
            matrix = self._resolve_buy(code, origin, destination, supplier_id)
            legacy_facts, legacy_state = self._legacy_buy(code, origin, destination, legacy_scopes.get(code))
            self._compare(lane, "BUY", code, "", legacy_facts, legacy_state, matrix)

    def _resolve_buy(self, code, origin, destination, supplier_id, weight=None):
        if supplier_id is None:
            return None
        return resolver.resolve(
            resolver.ResolutionContext(
                rate_type=resolver.BUY, direction="IMPORT", effective_date=self.quote_date, product_code=code,
                origin_iata=origin, destination_iata=destination, supplier_id=supplier_id,
                chargeable_weight=weight, allow_line_without_weight=weight is None,
            ),
            using=self.using,
        )

    def _legacy_buy(self, code, origin, destination, scope):
        product_id = self._product_id(code)
        if product_id is None:
            return None, ("ABSENT", "No legacy ProductCode with this code.")
        metadata = {"rate_scope": scope} if scope in ("ORIGIN", "DESTINATION") else {}
        try:
            selected = select_import_cogs_rate(RateSelectionContext(
                product_code_id=product_id, quote_date=self.quote_date, origin_airport=origin,
                destination_airport=destination, agent_id=self.agent_id, metadata=metadata,
            ))
        except RateNotFoundError:
            return None, ("ABSENT", "No legacy ImportCOGS row selected.")
        except RateAmbiguityError as exc:
            return None, ("AMBIGUOUS", f"Legacy selector reported ambiguity: {exc}")
        return self._import_cogs_facts(selected.record, selected), ("PRESENT", "")

    @staticmethod
    def _import_cogs_facts(row: ImportCOGS, selected) -> Facts:
        pct_base = row.product_code.percent_of_product_code
        tiers: tuple[tuple[str, str], ...] = ()
        basis = "UNKNOWN"
        unit = additive = pct = pct_basis = None
        if row.weight_breaks:
            basis = "TIERED_WEIGHT"
            tiers = tuple(sorted(
                ((_fmt(Decimal(str(t["min_kg"]))), _fmt(Decimal(str(t["rate"])))) for t in row.weight_breaks),
                key=lambda pair: Decimal(pair[0]),
            ))
        elif row.percent_rate is not None:
            basis, pct, pct_basis = "PERCENTAGE", _fmt(row.percent_rate), pct_base.code if pct_base else None
        elif row.is_additive and row.rate_per_kg is not None and row.rate_per_shipment is not None:
            basis, unit, additive = "PER_KG", _fmt(row.rate_per_kg), _fmt(row.rate_per_shipment)
        elif row.rate_per_kg is not None:
            basis, unit = "PER_KG", _fmt(row.rate_per_kg)
        elif row.rate_per_shipment is not None:
            basis, unit = "FLAT", _fmt(row.rate_per_shipment)
        return Facts(
            currency=row.currency, basis=basis, unit_rate=unit, additive_flat_amount=additive,
            min_charge=_fmt(row.min_charge), max_charge=_fmt(row.max_charge), percentage_rate=pct,
            percentage_basis=pct_basis, tiers=tiers, validity=_validity(row.valid_from, row.valid_until),
            origin=row.origin_airport or None, destination=row.destination_airport or None,
            provenance={
                "model": "ImportCOGS", "id": row.id, "scope": row.scope, "stage": selected.stage,
                "match_type": selected.match_type, "fallback_applied": selected.fallback_applied,
            },
        )

    # ---------------------------------------------------------------- SELL (LocalSellRate)

    def _sell_destination(self, destination: str) -> None:
        lane = f"*-{destination}"
        destination_location = self._location(destination)
        if destination_location is None:
            self.report.notes.append(f"{lane}: IATA does not resolve; destination SELL not comparable.")
            return
        origin_iata = self.lanes[0][0]
        matrix_codes = set(
            RateLine.objects.using(self.using)
            .filter(
                applicability__destination=destination_location, sheet__is_active=True,
                sheet__rate_type=resolver.SELL, sheet__valid_from__lte=self.quote_date,
            )
            .filter(Q(sheet__valid_until__isnull=True) | Q(sheet__valid_until__gte=self.quote_date))
            .values_list("product_code__code", flat=True)
        )
        legacy_codes = set(
            LocalSellRate.objects.using(self.using)
            .filter(
                location=destination, direction="IMPORT", valid_from__lte=self.quote_date,
                valid_until__gte=self.quote_date,
            )
            .values_list("product_code__code", flat=True)
        )
        origin_country = (self._location(origin_iata).country_code or "").upper()
        destination_country = (destination_location.country_code or "").upper()
        for term in PAYMENT_TERMS:
            currency = determine_quote_currency("IMPORT", term, origin_country, destination_country)
            for code in sorted(matrix_codes | legacy_codes):
                matrix = resolver.resolve(
                    resolver.ResolutionContext(
                        rate_type=resolver.SELL, direction="IMPORT", effective_date=self.quote_date,
                        product_code=code, origin_iata=origin_iata, destination_iata=destination,
                        payment_term=term, quote_currency=currency, allow_line_without_weight=True,
                    ),
                    using=self.using,
                )
                legacy_facts, state = self._legacy_sell(code, destination, term, currency)
                self._compare(lane, "SELL", code, f"{term}/{currency}", legacy_facts, state, matrix)

    def _legacy_sell(self, code, destination, term, currency):
        product = ProductCode.objects.using(self.using).filter(code=code).select_related(
            "percent_of_product_code"
        ).first()
        if product is None:
            return None, ("ABSENT", "No legacy ProductCode with this code.")
        base_qs = LocalSellRate.objects.using(self.using).filter(
            product_code=product, location=destination, direction="IMPORT", payment_term__in=[term, "ANY"],
            valid_from__lte=self.quote_date, valid_until__gte=self.quote_date,
        )
        if product.default_unit == ProductCode.UNIT_PERCENT:
            base_qs = base_qs.filter(rate_type="PERCENT", percent_of_product_code__isnull=False)
        else:
            base_qs = base_qs.exclude(rate_type="PERCENT")
        try:
            selected = select_local_sell_rate(
                RateSelectionContext(
                    product_code_id=product.id, quote_date=self.quote_date, location=destination,
                    direction="IMPORT", payment_term=term, currency=currency,
                ),
                queryset_override=base_qs, allow_pgk_fallback=False,
            )
        except RateNotFoundError:
            return None, ("ABSENT", "No legacy LocalSellRate row selected.")
        except RateAmbiguityError as exc:
            return None, ("AMBIGUOUS", f"Legacy selector reported ambiguity: {exc}")
        row = selected.record
        pct_base = row.percent_of_product_code
        basis = {"FIXED": "FLAT", "PER_KG": "PER_KG", "PERCENT": "PERCENTAGE"}.get(row.rate_type, f"UNKNOWN:{row.rate_type}")
        tiers: tuple[tuple[str, str], ...] = ()
        unit = additive = pct = pct_basis = None
        if row.weight_breaks:
            basis = "TIERED_WEIGHT"
            tiers = tuple(sorted(
                ((_fmt(Decimal(str(t["min_kg"]))), _fmt(Decimal(str(t["rate"])))) for t in row.weight_breaks),
                key=lambda pair: Decimal(pair[0]),
            ))
        elif basis == "PERCENTAGE":
            pct, pct_basis = _fmt(row.amount), pct_base.code if pct_base else None
        else:
            unit = _fmt(row.amount)
            if row.is_additive:
                additive = _fmt(row.additive_flat_amount)
        return Facts(
            currency=row.currency, basis=basis, unit_rate=unit, additive_flat_amount=additive,
            min_charge=_fmt(row.min_charge), max_charge=_fmt(row.max_charge), percentage_rate=pct,
            percentage_basis=pct_basis, tiers=tiers, validity=_validity(row.valid_from, row.valid_until),
            origin=None, destination=row.location,
            provenance={
                "model": "LocalSellRate", "id": row.id, "payment_term": row.payment_term, "stage": selected.stage,
                "match_type": selected.match_type, "fallback_applied": selected.fallback_applied,
            },
        ), ("PRESENT", "")

    # ---------------------------------------------------------------- comparison

    @staticmethod
    def _matrix_facts(tariff: resolver.ResolvedTariff) -> Facts:
        return Facts(
            currency=tariff.currency_code, basis=tariff.rate_basis, unit_rate=_fmt(tariff.unit_rate),
            additive_flat_amount=_fmt(tariff.additive_flat_amount), min_charge=_fmt(tariff.min_charge),
            max_charge=_fmt(tariff.max_charge), percentage_rate=_fmt(tariff.percentage_rate),
            percentage_basis=tariff.percentage_basis_product_code,
            tiers=tuple((_fmt(t.min_quantity), _fmt(t.unit_rate)) for t in tariff.tiers),
            validity=_validity(tariff.valid_from, tariff.valid_until), origin=tariff.origin_iata,
            destination=tariff.destination_iata,
            provenance={
                "model": "RateLine", "line_id": str(tariff.line_id), "sheet": tariff.sheet_name,
                "version": tariff.sheet_version, "source_reference": tariff.source_reference,
            },
        )

    def _compare(self, lane, side, code, context, legacy: Facts | None, legacy_state, matrix) -> None:
        def emit(aspect, cls, legacy_value=None, matrix_value=None, reason=""):
            self._emit(lane, side, code, aspect, cls, legacy_value, matrix_value, context, reason)

        matrix_state = "NOT_RESOLVED" if matrix is None else matrix.outcome
        matrix_facts = self._matrix_facts(matrix.tariff) if matrix is not None and matrix.matched else None

        provenance = {"lane": lane, "side": side, "product_code": code, "context": context}
        if legacy is not None:
            provenance["legacy"] = legacy.provenance
        if matrix_facts is not None:
            provenance["matrix"] = matrix_facts.provenance
        self.report.provenance.append(provenance)

        if legacy is None and legacy_state[0] == "ABSENT" and matrix_state == resolver.NO_MATCH:
            return  # Neither side prices this charge in this context; there is nothing to compare.
        if legacy is not None and matrix_facts is not None:
            emit("presence", MATCH, "present", "present")
        elif legacy is not None and matrix_state == resolver.NO_MATCH:
            emit("presence", LEGACY_ONLY, "present", "absent", "Legacy has a rate; the Rate Matrix has none.")
            return
        elif legacy is None and legacy_state[0] == "ABSENT" and matrix_facts is not None:
            emit("presence", RATE_MATRIX_ONLY, "absent", "present", "The Rate Matrix has a tariff; legacy has no row.")
            return
        else:
            detail = legacy_state[1] if legacy is None and legacy_state[0] != "ABSENT" else (
                "; ".join(matrix.reasons) if matrix is not None and not matrix.matched else
                "Rate Matrix side could not be resolved (no single supplier)."
            )
            emit("presence", NOT_COMPARABLE, legacy_state[0] if legacy is None else "present", matrix_state, detail)
            return

        basis_differs = legacy.basis != matrix_facts.basis
        if basis_differs:
            emit("basis", UNEXPLAINED_DIFFERENCE, legacy.basis, matrix_facts.basis)
        else:
            emit("basis", MATCH, legacy.basis, matrix_facts.basis)
        for aspect in VALUE_ASPECTS:
            left, right = getattr(legacy, aspect), getattr(matrix_facts, aspect)
            if aspect == "tiers":
                left, right = _render_tiers(left), _render_tiers(right)
            stated = any(value not in (None, "", EMPTY_TIERS) for value in (left, right))
            if basis_differs and aspect in BASIS_DEPENDENT_ASPECTS and stated:
                emit(aspect, NOT_COMPARABLE, left, right, "Rate basis differs; the value is not comparable.")
            elif left != right:
                emit(aspect, UNEXPLAINED_DIFFERENCE, left, right)
            elif stated:
                emit(aspect, MATCH, left, right)
        for aspect in ("validity", "origin", "destination"):
            left, right = getattr(legacy, aspect), getattr(matrix_facts, aspect)
            emit(aspect, MATCH if left == right else UNEXPLAINED_DIFFERENCE, left, right)

        if legacy.basis == "TIERED_WEIGHT" and matrix_facts.basis == "TIERED_WEIGHT":
            self._compare_weights(lane, side, code, context, legacy, matrix)

    def _compare_weights(self, lane, side, code, context, legacy: Facts, matrix) -> None:
        for weight in self.weights:
            legacy_rate = _legacy_tier_rate(legacy.tiers, weight)
            if side == "BUY":
                supplier = matrix.tariff.supplier_id if matrix.tariff else None
                origin, destination = lane.split("-")
                resolved = self._resolve_buy(code, origin, destination, supplier, weight)
            else:
                resolved = None
            tier = resolved.tariff.selected_tier if resolved is not None and resolved.matched else None
            matrix_rate = _fmt(tier.unit_rate) if tier else None
            aspect = f"rate@{_fmt(weight)}kg"
            if legacy_rate == matrix_rate:
                self._emit(lane, side, code, aspect, MATCH, legacy_rate, matrix_rate, context)
            else:
                self._emit(lane, side, code, aspect, UNEXPLAINED_DIFFERENCE, legacy_rate, matrix_rate, context)


def _render_tiers(tiers: tuple[tuple[str, str], ...]) -> str:
    if not tiers:
        return EMPTY_TIERS
    return "|".join(f"{lower}:{rate}" for lower, rate in tiers)


def _legacy_tier_rate(tiers: tuple[tuple[str, str], ...], weight: Decimal) -> str | None:
    """Mirror core.charge_rules.evaluate_tiered_break_rule's rate selection (locked by a test).

    The highest break at or below the weight applies; below the first break the lowest
    break's rate applies.
    """
    if not tiers:
        return None
    ordered = sorted(((Decimal(lower), rate) for lower, rate in tiers), reverse=True)
    selected = ordered[-1][1]
    for lower, rate in ordered:
        if weight >= lower:
            selected = rate
            break
    return selected
