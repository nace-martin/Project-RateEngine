"""Pilot Gate B3J: read-only Rate Matrix resolver.

Every value here is synthetic test data. No real tariff, party, or rate appears.
"""

import re
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_resolver import (
    AMBIGUOUS,
    EXACT_MATCH,
    INVALID_CONTEXT,
    NO_MATCH,
    ResolutionContext,
    resolve,
)

FREIGHT = "IMP-SYNTH-FRT"
FEE = "IMP-SYNTH-FEE"
ZERO = "IMP-SYNTH-ZERO"
PCT = "IMP-SYNTH-PCT"
TODAY = date(2030, 6, 15)


@pytest.fixture
def world(db):
    for code in ("XTS", "XXA", "XYY"):
        Currency.objects.get_or_create(code=code, defaults={"name": f"Synthetic {code}"})
    places = {}
    for iata in ("XAA", "XBB", "XCC", "XPM"):
        location = GeoLocation(canonical_name=f"Synthetic {iata}", country_code="ZZ", location_type="AIRPORT")
        location.save()
        GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=iata)
        places[iata] = location
    suppliers = {}
    for name in ("Synthetic Carrier A", "Synthetic Carrier B"):
        party = PartyMaster.objects.create(legal_name=name, entity_type="COMPANY", country_code="ZZ")
        PartyRole.objects.create(party=party, role_type="CARRIER")
        suppliers[name[-1]] = party
    codes = {}
    for code, category, basis in (
        (FREIGHT, "FREIGHT", "TIERED_WEIGHT"), (FEE, "DESTINATION", "FLAT"),
        (ZERO, "DESTINATION", "FLAT"), (PCT, "DESTINATION", "PERCENTAGE"),
    ):
        codes[code] = CommercialProductCode.objects.create(
            code=code, name=f"Synthetic {code}", category=category, sub_category="",
            gst_treatment="STANDARD", charge_basis_default=basis, is_active=True,
        )
    return {
        "places": places, "suppliers": suppliers, "codes": codes,
        "user": get_user_model().objects.create_user(username="synthetic-resolver", password="x"),
    }


def sheet(world, name, rate_type, currency, *, supplier=None, valid_from=date(2030, 1, 1),
          valid_until=date(2030, 12, 31), active=True, version=1):
    return RateSheet.objects.create(
        name=name, version=version, rate_type=rate_type, transport_mode="AIR", currency_code=currency,
        valid_from=valid_from, valid_until=valid_until, is_active=active, source_reference="SYNTHETIC-TEST",
        carrier=world["suppliers"][supplier] if supplier else None, created_by=world["user"],
    )


def line(world, sheet_, code, basis, *, origin="XAA", destination=None, direction="IMPORT", payment_term="",
         service_level="", commodity="", equipment="", tiers=(), **amounts):
    rate_line = RateLine.objects.create(
        sheet=sheet_, product_code=world["codes"][code], rate_basis=basis,
        percentage_basis_product_code=world["codes"][amounts.pop("pct_basis")] if "pct_basis" in amounts else None,
        **amounts,
    )
    RateApplicability.objects.create(
        rate_line=rate_line, direction=direction, payment_term=payment_term, service_level=service_level,
        commodity_category=commodity, equipment_type=equipment,
        origin=world["places"][origin] if origin else None,
        destination=world["places"][destination] if destination else None,
    )
    for lower, upper, rate in tiers:
        RateTier.objects.create(rate_line=rate_line, min_quantity=D(lower), max_quantity=None if upper is None else D(upper), unit_rate=D(rate))
    return rate_line


TIERS = (("0", "45", "7.50"), ("45", "100", "7.35"), ("100", "250", "7.00"), ("250", "500", "6.75"),
         ("500", "1000", "6.45"), ("1000", None, "6.10"))


def buy(world, **overrides):
    values = {
        "rate_type": "BUY", "direction": "IMPORT", "effective_date": TODAY, "product_code": FREIGHT, "origin_iata": "XAA",
        "destination_iata": "XPM", "supplier_id": world["suppliers"]["A"].id,
    }
    values.update(overrides)
    return ResolutionContext(**values)


def sell(**overrides):
    values = {
        "rate_type": "SELL", "direction": "IMPORT", "effective_date": TODAY, "product_code": FEE, "origin_iata": "XAA",
        "destination_iata": "XPM", "quote_currency": "XTS",
    }
    values.update(overrides)
    return ResolutionContext(**values)


@pytest.fixture
def freight(world):
    s = sheet(world, "Synthetic BUY", "BUY", "XTS", supplier="A")
    line(world, s, FREIGHT, "TIERED_WEIGHT", destination="XPM", min_charge=D(350), tiers=TIERS)
    return s


# --------------------------------------------------------------------------- tiers


@pytest.mark.django_db
class TestTierBoundaries:
    @pytest.mark.parametrize(
        ("weight", "rate"),
        [
            ("1", "7.50"), ("44.9999", "7.50"), ("45", "7.35"), ("99.9999", "7.35"), ("100", "7.00"),
            ("249", "7.00"), ("250", "6.75"), ("499", "6.75"), ("500", "6.45"), ("999.9999", "6.45"),
            ("1000", "6.10"), ("1000.0001", "6.10"), ("50000", "6.10"),
        ],
    )
    def test_lower_inclusive_upper_exclusive_whole_weight(self, world, freight, weight, rate):
        result = resolve(buy(world, chargeable_weight=D(weight)))
        assert result.outcome == EXACT_MATCH, result.reasons
        assert result.tariff.selected_tier.unit_rate == D(rate)
        assert result.tariff.min_charge == D(350)

    def test_zero_weight_uses_the_first_tier(self, world, freight):
        assert resolve(buy(world, chargeable_weight=D(0))).tariff.selected_tier.unit_rate == D("7.50")

    def test_weight_is_required_for_a_tiered_rate(self, world, freight):
        result = resolve(buy(world))
        assert result.outcome == INVALID_CONTEXT
        assert "chargeable_weight" in result.reasons[0]

    def test_structural_lookup_returns_the_line_without_a_tier(self, world, freight):
        result = resolve(buy(world, allow_line_without_weight=True))
        assert result.outcome == EXACT_MATCH
        assert result.tariff.selected_tier is None
        assert len(result.tariff.tiers) == 6

    def test_negative_weight_is_invalid(self, world, freight):
        assert resolve(buy(world, chargeable_weight=D(-1))).outcome == INVALID_CONTEXT

    def test_weight_below_first_tier_is_not_priced(self, world):
        s = sheet(world, "Synthetic BUY", "BUY", "XTS", supplier="A")
        line(world, s, FREIGHT, "TIERED_WEIGHT", destination="XPM", tiers=(("45", None, "7.35"),))
        result = resolve(buy(world, chargeable_weight=D(30)))
        assert result.outcome == NO_MATCH
        assert "not priced" in result.reasons[0]


# --------------------------------------------------------------------------- context


@pytest.mark.django_db
class TestInvalidContext:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"rate_type": "COST"}, {"direction": "SIDEWAYS"}, {"transport_mode": "SEA"}, {"product_code": ""},
            {"payment_term": "NET30"}, {"service_level": "FAST"}, {"supplier_id": None},
            {"origin_iata": "xaa"}, {"effective_date": "2030-06-15"},
        ],
    )
    def test_invalid_buy_context(self, world, freight, overrides):
        result = resolve(buy(world, chargeable_weight=D(50), **overrides))
        assert result.outcome == INVALID_CONTEXT
        assert result.tariff is None

    def test_missing_buy_supplier_never_falls_back_to_any_supplier(self, world, freight):
        assert resolve(buy(world, supplier_id=None, chargeable_weight=D(50))).outcome == INVALID_CONTEXT

    def test_sell_requires_a_quote_currency_and_no_supplier(self, world):
        assert resolve(sell(quote_currency=None)).outcome == INVALID_CONTEXT
        assert resolve(sell(supplier_id=world["suppliers"]["A"].id)).outcome == INVALID_CONTEXT

    def test_unknown_airport_is_invalid(self, world, freight):
        result = resolve(buy(world, origin_iata="QQQ", chargeable_weight=D(50)))
        assert result.outcome == INVALID_CONTEXT
        assert "QQQ" in result.reasons[0]

    def test_inactive_airport_is_invalid(self, world, freight):
        world["places"]["XCC"].is_active = False
        world["places"]["XCC"].save()
        assert resolve(buy(world, origin_iata="XCC", chargeable_weight=D(50))).outcome == INVALID_CONTEXT


# --------------------------------------------------------------------------- coverage


@pytest.mark.django_db
class TestNoMatch:
    def test_wrong_direction(self, world, freight):
        assert resolve(buy(world, direction="EXPORT", chargeable_weight=D(50))).outcome == NO_MATCH

    def test_reverse_direction_is_not_inferred(self, world, freight):
        reverse = buy(world, origin_iata="XPM", destination_iata="XAA", chargeable_weight=D(50))
        assert resolve(reverse).outcome == NO_MATCH
        assert resolve(buy(world, direction="EXPORT", origin_iata="XPM", destination_iata="XAA",
                           chargeable_weight=D(50))).outcome == NO_MATCH

    def test_unsupported_route(self, world, freight):
        assert resolve(buy(world, origin_iata="XBB", chargeable_weight=D(50))).outcome == NO_MATCH
        assert resolve(buy(world, destination_iata="XCC", chargeable_weight=D(50))).outcome == NO_MATCH

    def test_unknown_product_code(self, world, freight):
        assert resolve(buy(world, product_code=FEE, chargeable_weight=D(50))).outcome == NO_MATCH

    def test_wrong_supplier(self, world, freight):
        other = buy(world, supplier_id=world["suppliers"]["B"].id, chargeable_weight=D(50))
        assert resolve(other).outcome == NO_MATCH

    def test_wrong_mode_commodity_and_equipment_do_not_match(self, world, freight):
        s = sheet(world, "Synthetic SELL SPECIAL", "SELL", "XTS")
        line(world, s, FEE, "FLAT", destination="XPM", commodity="DG", unit_rate=D(9))
        assert resolve(sell(commodity_category="")).outcome == NO_MATCH
        assert resolve(sell(commodity_category="DG")).outcome == EXACT_MATCH
        assert resolve(sell(commodity_category="GCR")).outcome == NO_MATCH

    def test_inactive_sheet_is_ignored(self, world):
        s = sheet(world, "Synthetic BUY OFF", "BUY", "XTS", supplier="A", active=False)
        line(world, s, FREIGHT, "TIERED_WEIGHT", destination="XPM", tiers=TIERS)
        assert resolve(buy(world, chargeable_weight=D(50))).outcome == NO_MATCH

    def test_sell_never_resolves_as_buy_and_vice_versa(self, world, freight):
        assert resolve(sell(product_code=FREIGHT, quote_currency="XTS")).outcome == NO_MATCH


@pytest.mark.django_db
class TestValidity:
    def test_inclusive_window_edges(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS", valid_from=date(2030, 3, 1), valid_until=date(2030, 3, 31))
        line(world, s, FEE, "FLAT", destination="XPM", unit_rate=D(100))
        for day, expected in ((date(2030, 2, 28), NO_MATCH), (date(2030, 3, 1), EXACT_MATCH),
                              (date(2030, 3, 31), EXACT_MATCH), (date(2030, 4, 1), NO_MATCH)):
            assert resolve(sell(effective_date=day)).outcome == expected, day

    def test_open_ended_sheet_matches_any_later_date(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS", valid_from=date(2030, 1, 1), valid_until=None)
        line(world, s, FEE, "FLAT", destination="XPM", unit_rate=D(100))
        assert resolve(sell(effective_date=date(2099, 1, 1))).outcome == EXACT_MATCH
        assert resolve(sell(effective_date=date(2029, 12, 31))).outcome == NO_MATCH


# --------------------------------------------------------------------------- SELL currency and payment term


@pytest.mark.django_db
class TestSell:
    @pytest.fixture
    def three_currencies(self, world):
        for currency, amount in (("XTS", "165"), ("XXA", "80"), ("XYY", "60")):
            s = sheet(world, f"Synthetic SELL {currency}", "SELL", currency)
            line(world, s, FEE, "FLAT", origin=None, destination="XPM", unit_rate=D(amount))

    @pytest.mark.parametrize(("currency", "amount"), [("XTS", "165"), ("XXA", "80"), ("XYY", "60")])
    def test_selection_is_by_requested_currency_with_no_fx(self, world, three_currencies, currency, amount):
        result = resolve(sell(quote_currency=currency))
        assert result.outcome == EXACT_MATCH
        assert result.tariff.currency_code == currency
        assert result.tariff.unit_rate == D(amount)

    def test_wrong_currency_never_falls_back(self, world, three_currencies):
        result = resolve(sell(quote_currency="USD"))
        assert result.outcome == NO_MATCH

    def test_blank_payment_term_applies_to_prepaid_and_collect(self, world, three_currencies):
        for term in ("", "PREPAID", "COLLECT"):
            assert resolve(sell(payment_term=term)).outcome == EXACT_MATCH, term

    def test_specific_payment_term_matches_only_that_term(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS")
        line(world, s, FEE, "FLAT", origin=None, destination="XPM", payment_term="PREPAID", unit_rate=D(10))
        assert resolve(sell(payment_term="PREPAID")).outcome == EXACT_MATCH
        assert resolve(sell(payment_term="COLLECT")).outcome == NO_MATCH
        assert resolve(sell(payment_term="")).outcome == NO_MATCH

    def test_blank_and_specific_payment_term_coexisting_is_ambiguous(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS")
        line(world, s, FEE, "FLAT", origin=None, destination="XPM", payment_term="PREPAID", unit_rate=D(10))
        other = sheet(world, "Synthetic SELL ANY", "SELL", "XTS")
        line(world, other, FEE, "FLAT", origin=None, destination="XPM", payment_term="", unit_rate=D(12))
        result = resolve(sell(payment_term="PREPAID"))
        assert result.outcome == AMBIGUOUS
        assert {c.unit_rate for c in result.candidates} == {D(10), D(12)}
        assert result.tariff is None
        # COLLECT only sees the blank-term line, so it is not ambiguous.
        assert resolve(sell(payment_term="COLLECT")).outcome == EXACT_MATCH


# --------------------------------------------------------------------------- ambiguity


@pytest.mark.django_db
class TestAmbiguity:
    def test_overlapping_duplicates_are_ambiguous_and_no_precedence_is_applied(self, world):
        for version in (1, 2):
            s = sheet(world, "Synthetic SELL", "SELL", "XTS", version=version)
            line(world, s, FEE, "FLAT", origin=None, destination="XPM", unit_rate=D(10 + version))
        result = resolve(sell())
        assert result.outcome == AMBIGUOUS
        assert [c.sheet_version for c in result.candidates] == [1, 2]

    def test_blank_origin_overlapping_a_specific_origin_is_ambiguous(self, world):
        general = sheet(world, "Synthetic SELL GENERAL", "SELL", "XTS")
        line(world, general, FEE, "FLAT", origin=None, destination="XPM", unit_rate=D(10))
        specific = sheet(world, "Synthetic SELL SPECIFIC", "SELL", "XTS")
        line(world, specific, FEE, "FLAT", origin="XAA", destination="XPM", unit_rate=D(12))
        assert resolve(sell()).outcome == AMBIGUOUS
        # Another origin only sees the general line.
        assert resolve(sell(origin_iata="XBB")).outcome == EXACT_MATCH

    def test_buy_costs_in_different_currencies_stay_ambiguous(self, world):
        for currency in ("XTS", "XXA"):
            s = sheet(world, f"Synthetic BUY {currency}", "BUY", currency, supplier="A")
            line(world, s, FEE, "FLAT", origin="XAA", destination="XPM", unit_rate=D(50))
        result = resolve(buy(world, product_code=FEE))
        assert result.outcome == AMBIGUOUS
        assert {c.currency_code for c in result.candidates} == {"XTS", "XXA"}

    def test_two_suppliers_do_not_compete_when_one_is_named(self, world):
        for who in ("A", "B"):
            s = sheet(world, f"Synthetic BUY {who}", "BUY", "XTS", supplier=who)
            line(world, s, FEE, "FLAT", origin="XAA", destination="XPM", unit_rate=D(50) if who == "A" else D(60))
        result = resolve(buy(world, product_code=FEE))
        assert result.outcome == EXACT_MATCH
        assert result.tariff.unit_rate == D(50)


# --------------------------------------------------------------------------- facts


@pytest.mark.django_db
class TestFacts:
    def test_legitimate_zero_rate_is_a_match_not_missing(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS")
        line(world, s, ZERO, "FLAT", origin=None, destination="XPM", unit_rate=D(0))
        result = resolve(sell(product_code=ZERO))
        assert result.outcome == EXACT_MATCH
        assert result.tariff.unit_rate == D(0)

    def test_native_facts_and_provenance(self, world, freight):
        result = resolve(buy(world, chargeable_weight=D(100)))
        facts = result.tariff.as_dict()
        assert facts["sheet_name"] == "Synthetic BUY"
        assert facts["sheet_version"] == 1
        assert facts["source_reference"] == "SYNTHETIC-TEST"
        assert facts["supplier_name"] == "Synthetic Carrier A"
        assert facts["currency_code"] == "XTS"
        assert (facts["valid_from"], facts["valid_until"]) == ("2030-01-01", "2030-12-31")
        assert facts["rate_basis"] == "TIERED_WEIGHT"
        assert facts["min_charge"] == "350.0000"
        assert facts["selected_tier"] == {"min_quantity": "100.0000", "max_quantity": "250.0000", "unit_rate": "7.0000"}
        assert facts["applicability"]["origin_iata"] == "XAA"
        assert facts["applicability"]["destination_iata"] == "XPM"
        assert [t["min_quantity"] for t in facts["tiers"]] == ["0.0000", "45.0000", "100.0000", "250.0000", "500.0000", "1000.0000"]

    def test_additive_and_percentage_values_are_returned_unconverted(self, world):
        s = sheet(world, "Synthetic SELL", "SELL", "XTS")
        line(world, s, FEE, "PER_KG", origin=None, destination="XPM", unit_rate=D("0.22"),
             additive_flat_amount=D("4.50"), min_charge=D(20), max_charge=D(300))
        line(world, s, PCT, "PERCENTAGE", origin=None, destination="XPM", percentage_rate=D(10), pct_basis=FEE)
        fee = resolve(sell()).tariff
        assert (fee.rate_basis, fee.unit_rate, fee.additive_flat_amount, fee.min_charge, fee.max_charge) == (
            "PER_KG", D("0.22"), D("4.50"), D(20), D(300),
        )
        pct = resolve(sell(product_code=PCT)).tariff
        assert (pct.rate_basis, pct.percentage_rate, pct.percentage_basis_product_code, pct.unit_rate) == (
            "PERCENTAGE", D(10), FEE, None,
        )


# --------------------------------------------------------------------------- safety


@pytest.mark.django_db
class TestReadOnly:
    def test_resolution_issues_only_selects_and_touches_no_fx(self, world, freight):
        before = {m: m.objects.count() for m in (RateSheet, RateLine, RateApplicability, RateTier)}
        with CaptureQueriesContext(connection) as queries:
            for weight in ("10", "45", "5000"):
                resolve(buy(world, chargeable_weight=D(weight)))
            resolve(sell())
        verbs = {q["sql"].lstrip().split(None, 1)[0].upper() for q in queries}
        assert not verbs & {"INSERT", "UPDATE", "DELETE"}, verbs
        tables = {t.lower() for q in queries for t in re.findall(r'(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', q["sql"], re.IGNORECASE)}
        assert not {t for t in tables if "fx" in t}, tables
        assert {m: m.objects.count() for m in before} == before

    def test_results_are_deterministic(self, world, freight):
        a = resolve(buy(world, chargeable_weight=D(120))).as_dict()
        b = resolve(buy(world, chargeable_weight=D(120))).as_dict()
        assert a == b


LIVE_PATHS = ("quotes", "pricing_v4/engine", "pricing_v4/adapter.py", "pricing_v4/dispatcher.py", "core")
RESOLVER_MODULES = ("rate_matrix_resolver", "rate_matrix_shadow")


def test_no_live_pricing_module_imports_the_resolver_or_shadow():
    root = Path(__file__).resolve().parents[2]
    offenders = []
    for relative in LIVE_PATHS:
        base = root / relative
        files = [base] if base.is_file() else base.rglob("*.py")
        for path in files:
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(re.search(rf"\b{name}\b", text) for name in RESOLVER_MODULES):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"Live pricing modules must not use the Rate Matrix resolver: {offenders}"
