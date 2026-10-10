"""Pilot Gate B3J: Stage-1 read-only shadow comparison.

Every value here is synthetic test data. No real tariff, party, or rate appears.
"""

import json
from datetime import date
from decimal import Decimal as D
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.charge_rules import evaluate_tiered_break_rule
from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import Agent, ImportCOGS, LocalSellRate, ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services import rate_matrix_shadow as shadow
from pricing_v4.services.rate_matrix_shadow import (
    EXPECTED_DIFFERENCE,
    LEGACY_ONLY,
    MATCH,
    NOT_COMPARABLE,
    RATE_MATRIX_ONLY,
    UNEXPLAINED_DIFFERENCE,
    _legacy_tier_rate,
    load_registry,
    run_shadow,
)

TODAY = date(2030, 6, 15)
FRT, SCREEN, FEE, PCT = "IMP-SYNTH-FRT", "IMP-SYNTH-SCREEN", "IMP-SYNTH-FEE", "IMP-SYNTH-PCT"
LANE = "XAA-XPM"


def _legacy(pk, code, *, category, unit="SHIPMENT", domain="IMPORT", **extra):
    return ProductCode.objects.create(
        id=pk, code=code, description=f"Synthetic {code}", domain=domain, category=category,
        is_gst_applicable=True, gst_rate="0.10", gst_treatment="STANDARD", gl_revenue_code="4000",
        gl_cost_code="5000", default_unit=unit, **extra,
    )


@pytest.fixture
def world(db):
    for code in ("XTS", "XXA", "PGK", "AUD"):
        Currency.objects.get_or_create(code=code, defaults={"name": f"Synthetic {code}"})
    places = {}
    for iata, country in (("XAA", "AU"), ("XPM", "PG")):
        location = GeoLocation(canonical_name=f"Synthetic {iata}", country_code=country, location_type="AIRPORT")
        location.save()
        GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=iata)
        places[iata] = location
    party = PartyMaster.objects.create(legal_name="Synthetic Agent Pty", entity_type="COMPANY", country_code="ZZ")
    PartyRole.objects.create(party=party, role_type="AGENT")
    agent = Agent.objects.create(code="SYN-AGENT", name="Synthetic Agent", country_code="AU")
    products = {
        FRT: _legacy(98901, FRT, category="FREIGHT", unit="KG"),
        SCREEN: _legacy(98902, SCREEN, category="SCREENING", unit="KG"),
        FEE: _legacy(98903, FEE, category="HANDLING"),
    }
    products[PCT] = _legacy(98904, PCT, category="SURCHARGE", unit="PERCENT", percent_of_product_code=products[FEE])
    mirrors = {
        code: CommercialProductCode.objects.create(
            code=code, name=f"Synthetic {code}", category=category, sub_category="", gst_treatment="STANDARD",
            charge_basis_default=basis, is_active=True, legacy_product_code=products[code],
        )
        for code, category, basis in (
            (FRT, "FREIGHT", "TIERED_WEIGHT"), (SCREEN, "ORIGIN", "PER_KG"), (FEE, "DESTINATION", "FLAT"),
            (PCT, "DESTINATION", "PERCENTAGE"),
        )
    }
    return {
        "places": places, "party": party, "agent": agent, "products": products, "mirrors": mirrors,
        "user": get_user_model().objects.create_user(username="synthetic-shadow", password="x"),
    }


def matrix_sheet(world, name, rate_type, currency, *, supplier=True, valid_from=date(2030, 1, 1), valid_until=date(2030, 12, 31)):
    return RateSheet.objects.create(
        name=name, version=1, rate_type=rate_type, transport_mode="AIR", currency_code=currency,
        valid_from=valid_from, valid_until=valid_until, is_active=True, source_reference="SYNTHETIC-TEST",
        carrier=world["party"] if supplier else None, created_by=world["user"],
    )


def matrix_line(world, sheet, code, basis, *, origin="XAA", destination=None, tiers=(), pct_basis=None, **amounts):
    rate_line = RateLine.objects.create(
        sheet=sheet, product_code=world["mirrors"][code], rate_basis=basis,
        percentage_basis_product_code=world["mirrors"][pct_basis] if pct_basis else None, **amounts,
    )
    RateApplicability.objects.create(
        rate_line=rate_line, direction="IMPORT",
        origin=world["places"][origin] if origin else None,
        destination=world["places"][destination] if destination else None,
    )
    for lower, upper, rate in tiers:
        RateTier.objects.create(
            rate_line=rate_line, min_quantity=D(lower), max_quantity=None if upper is None else D(upper), unit_rate=D(rate)
        )


def legacy_cogs(world, code, **fields):
    defaults = {
        "product_code": world["products"][code], "origin_airport": "XAA", "destination_airport": None, "currency": "XTS",
        "agent": world["agent"], "valid_from": date(2030, 1, 1), "valid_until": date(2030, 12, 31), "scope": "ORIGIN",
    }
    defaults.update(fields)
    return ImportCOGS.objects.create(**defaults)


def legacy_sell(world, code, term="ANY", **fields):
    defaults = {
        "product_code": world["products"][code], "location": "XPM", "direction": "IMPORT", "payment_term": term,
        "currency": "PGK", "rate_type": "FIXED", "amount": D(100), "valid_from": date(2030, 1, 1),
        "valid_until": date(2030, 12, 31),
    }
    defaults.update(fields)
    return LocalSellRate.objects.create(**defaults)


FREIGHT_TIERS = (("0", "45", "7.50"), ("45", "100", "7.35"), ("100", None, "7.00"))
LEGACY_BREAKS = [{"min_kg": 45, "rate": "7.35"}, {"min_kg": 100, "rate": "7.00"}]


@pytest.fixture
def identical(world):
    """Matrix and legacy agree on a freight line, a screening line, and two destination SELL lines."""
    buy = matrix_sheet(world, "Synthetic BUY", "BUY", "XTS", valid_from=date(2030, 1, 1))
    matrix_line(world, buy, FRT, "TIERED_WEIGHT", destination="XPM", min_charge=D(350),
                tiers=(("45", None, "7.35"),) if False else FREIGHT_TIERS)
    matrix_line(world, buy, SCREEN, "PER_KG", unit_rate=D("0.38"), min_charge=D(70))
    legacy_cogs(world, FRT, destination_airport="XPM", scope="LANE", min_charge=D(350),
                weight_breaks=[{"min_kg": 0, "rate": "7.50"}] + LEGACY_BREAKS)
    legacy_cogs(world, SCREEN, rate_per_kg=D("0.38"), min_charge=D(70))

    sell = matrix_sheet(world, "Synthetic SELL PGK", "SELL", "PGK", supplier=False)
    matrix_line(world, sell, FEE, "FLAT", origin=None, destination="XPM", unit_rate=D(165))
    matrix_line(world, sell, PCT, "PERCENTAGE", origin=None, destination="XPM", percentage_rate=D(10), pct_basis=FEE)
    aud = matrix_sheet(world, "Synthetic SELL AUD", "SELL", "AUD", supplier=False)
    matrix_line(world, aud, FEE, "FLAT", origin=None, destination="XPM", unit_rate=D(80))
    legacy_sell(world, FEE, "ANY", currency="PGK", amount=D(165), valid_from=date(2030, 1, 1))
    legacy_sell(world, FEE, "ANY", currency="AUD", amount=D(80), valid_from=date(2030, 1, 1))
    legacy_sell(world, PCT, "ANY", currency="PGK", rate_type="PERCENT", amount=D(10),
                percent_of_product_code=world["products"][FEE], valid_from=date(2030, 1, 1))
    return world


def run(**kwargs):
    kwargs.setdefault("lanes", (("XAA", "XPM"),))
    kwargs.setdefault("weights", (D(30), D(45), D(100), D(1000)))
    return run_shadow(quote_date=TODAY, **kwargs)


def find(report, **match):
    return [r for r in report.records if all(getattr(r, k) == v for k, v in match.items())]


def snapshot():
    return {
        "matrix": [RateSheet.objects.count(), RateLine.objects.count(), RateApplicability.objects.count(),
                   RateTier.objects.count()],
        "cogs": list(ImportCOGS.objects.order_by("id").values()),
        "sell": list(LocalSellRate.objects.order_by("id").values()),
    }


# --------------------------------------------------------------------------- comparison


@pytest.mark.django_db
class TestComparison:
    def test_identical_data_matches_everywhere(self, identical):
        report = run()
        counts = report.counts()
        assert counts[UNEXPLAINED_DIFFERENCE] == counts[LEGACY_ONLY] == counts[RATE_MATRIX_ONLY] == 0, report.render_text()
        assert counts[NOT_COMPARABLE] == 0
        assert counts[MATCH] > 20
        assert {r.product_code for r in report.records} == {FRT, SCREEN, FEE, PCT}

    def test_value_difference_is_unexplained_never_normalised(self, identical):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.382"))
        report = run()
        diff = find(report, product_code=SCREEN, aspect="unit_rate")[0]
        assert diff.classification == UNEXPLAINED_DIFFERENCE
        assert (diff.legacy, diff.matrix) == ("0.382", "0.38")
        assert report.counts()[UNEXPLAINED_DIFFERENCE] == 1

    def test_registry_explains_only_the_exact_difference(self, identical):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.382"))
        entry = {
            "lane": LANE, "side": "BUY", "product_code": SCREEN, "aspect": "unit_rate", "legacy": "0.382",
            "matrix": "0.38", "reason": "Synthetic documented reason.", "evidence": "SYNTHETIC-EVIDENCE",
        }
        report = run(registry=[entry])
        diff = find(report, product_code=SCREEN, aspect="unit_rate")[0]
        assert diff.classification == EXPECTED_DIFFERENCE
        assert (diff.reason, diff.evidence) == ("Synthetic documented reason.", "SYNTHETIC-EVIDENCE")
        assert report.stale_registry_entries == []

    def test_registry_entry_for_other_values_is_stale_and_changes_nothing(self, identical):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.39"))
        entry = {
            "lane": LANE, "side": "BUY", "product_code": SCREEN, "aspect": "unit_rate", "legacy": "0.382",
            "matrix": "0.38", "reason": "Synthetic.", "evidence": "SYNTHETIC",
        }
        report = run(registry=[entry])
        assert find(report, product_code=SCREEN, aspect="unit_rate")[0].classification == UNEXPLAINED_DIFFERENCE
        assert report.stale_registry_entries == [entry]

    def test_legacy_only_and_matrix_only(self, identical):
        RateLine.objects.filter(product_code__code=SCREEN).delete()
        legacy_sell(identical, PCT, "ANY", currency="AUD", rate_type="PERCENT", amount=D(10),
                    percent_of_product_code=identical["products"][FEE], valid_from=date(2030, 1, 1))
        matrix_line(identical, RateSheet.objects.get(name="Synthetic SELL AUD"), SCREEN, "FLAT",
                    origin=None, destination="XPM", unit_rate=D(5))
        report = run()
        assert find(report, product_code=SCREEN, side="BUY", aspect="presence")[0].classification == LEGACY_ONLY
        assert find(report, product_code=SCREEN, side="SELL", aspect="presence")[0].classification == RATE_MATRIX_ONLY

    def test_different_basis_makes_rate_values_not_comparable_but_keeps_currency_and_minimum(self, identical):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=None, rate_per_shipment=D(30))
        report = run()
        by_aspect = {r.aspect: r for r in find(report, product_code=SCREEN)}
        assert by_aspect["basis"].classification == UNEXPLAINED_DIFFERENCE
        assert by_aspect["unit_rate"].classification == NOT_COMPARABLE
        assert by_aspect["currency"].classification == MATCH
        assert by_aspect["min_charge"].classification == MATCH

    def test_ambiguous_matrix_is_not_comparable_not_guessed(self, identical):
        rival = matrix_sheet(identical, "Synthetic BUY RIVAL", "BUY", "XXA")
        matrix_line(identical, rival, SCREEN, "PER_KG", unit_rate=D("0.50"))
        report = run()
        record = find(report, product_code=SCREEN, aspect="presence")[0]
        assert record.classification == NOT_COMPARABLE
        assert record.matrix == "AMBIGUOUS"

    def test_validity_and_applicability_are_compared(self, identical):
        ImportCOGS.objects.filter(product_code__code=FRT).update(valid_from=date(2029, 1, 1))
        report = run()
        diff = find(report, product_code=FRT, aspect="validity")[0]
        assert diff.classification == UNEXPLAINED_DIFFERENCE
        assert find(report, product_code=FRT, aspect="destination")[0].classification == MATCH

    def test_payment_term_and_currency_follow_the_canonical_quote_currency_policy(self, identical):
        report = run()
        contexts = {r.context for r in report.records if r.side == "SELL"}
        # IMPORT COLLECT quotes PGK; IMPORT PREPAID from AU quotes AUD.
        assert contexts == {"COLLECT/PGK", "PREPAID/AUD"}


# --------------------------------------------------------------------------- weights


@pytest.mark.django_db
class TestWeights:
    def test_below_first_legacy_break_uses_lowest_break_rate_and_is_flagged(self, identical):
        ImportCOGS.objects.filter(product_code__code=FRT).update(weight_breaks=LEGACY_BREAKS)
        report = run(weights=(D(30), D("44.9999"), D(45), D(100), D(1000)))
        by_aspect = {r.aspect: r for r in find(report, product_code=FRT) if r.aspect.startswith("rate@")}
        assert (by_aspect["rate@30kg"].legacy, by_aspect["rate@30kg"].matrix) == ("7.35", "7.5")
        assert by_aspect["rate@30kg"].classification == UNEXPLAINED_DIFFERENCE
        assert by_aspect["rate@44.9999kg"].classification == UNEXPLAINED_DIFFERENCE
        for aspect in ("rate@45kg", "rate@100kg", "rate@1000kg"):
            assert by_aspect[aspect].classification == MATCH, aspect
        assert find(report, product_code=FRT, aspect="tiers")[0].classification == UNEXPLAINED_DIFFERENCE

    @pytest.mark.parametrize(
        ("weight", "rate"),
        [("1", "7.50"), ("44", "7.50"), ("45", "7.35"), ("99", "7.35"), ("100", "7.00"), ("250", "7.00"), ("1000", "7.00")],
    )
    def test_weight_points_match_when_both_sides_agree(self, identical, weight, rate):
        report = run(weights=(D(weight),))
        record = find(report, product_code=FRT, aspect=f"rate@{weight}kg")[0]
        assert record.classification == MATCH
        assert record.matrix == rate.rstrip("0").rstrip(".") if "." in rate else rate

    @pytest.mark.parametrize("weight", ["0", "1", "44", "45", "46", "99", "100", "249", "250", "499", "500", "999", "1000", "1001"])
    def test_legacy_rate_mirror_agrees_with_the_production_rule(self, weight):
        breaks = [{"min_kg": 45, "rate": "7.35"}, {"min_kg": 100, "rate": "7.00"}, {"min_kg": 250, "rate": "6.75"},
                  {"min_kg": 500, "rate": "6.45"}, {"min_kg": 1000, "rate": "6.10"}]
        tiers = tuple((str(b["min_kg"]), b["rate"].rstrip("0").rstrip(".") if "." in b["rate"] else b["rate"]) for b in breaks)
        chosen = D(_legacy_tier_rate(tiers, D(weight)))
        # Production evaluates amount = rate * quantity, with no limits applied.
        amount = evaluate_tiered_break_rule(breaks, D(weight)).amount
        assert amount == (chosen * D(weight)).quantize(D("0.01"))


# --------------------------------------------------------------------------- safety


@pytest.mark.django_db
class TestSafety:
    def test_shadow_run_writes_nothing_and_computes_no_money(self, identical):
        before = snapshot()
        with CaptureQueriesContext(connection) as queries:
            report = run()
        assert snapshot() == before
        verbs = {q["sql"].lstrip().split(None, 1)[0].upper() for q in queries}
        assert not verbs & {"INSERT", "UPDATE", "DELETE"}, verbs
        assert not any("fx" in q["sql"].lower() or "caf" in q["sql"].lower() for q in queries)
        assert report.as_dict()["writes_performed"] == 0
        assert connection.in_atomic_block

    def test_connection_is_writable_after_the_run(self, identical):
        run()
        PartyMaster.objects.create(legal_name="Synthetic After", entity_type="COMPANY", country_code="ZZ")

    def test_no_totals_gst_or_fx_fields_in_the_report(self, identical):
        text = run().render_json().lower()
        for forbidden in ("total", "gst_amount", "caf", "margin", "fx_rate"):
            assert forbidden not in text

    def test_report_is_deterministic(self, identical):
        assert run().render_json() == run().render_json()

    def test_expired_matrix_sheet_is_not_compared_as_present(self, identical):
        report = run_shadow(quote_date=date(2031, 6, 15), lanes=(("XAA", "XPM"),), weights=(D(50),))
        assert report.counts()[MATCH] == 0


# --------------------------------------------------------------------------- registry and command


def test_registry_must_be_strict():
    good = {"registry_version": 1, "entries": [{
        "lane": "*", "side": "BUY", "product_code": "X", "aspect": "tiers", "legacy": "a", "matrix": "b",
        "reason": "r", "evidence": "e",
    }]}
    entries, errors = load_registry(json.dumps(good))
    assert len(entries) == 1 and errors == []
    assert load_registry("{not json")[1]
    assert load_registry(json.dumps({"registry_version": 2, "entries": []}))[1]
    bad = json.loads(json.dumps(good))
    bad["entries"][0]["reason"] = ""
    assert load_registry(json.dumps(bad))[1]
    bad["entries"][0].pop("reason")
    assert load_registry(json.dumps(bad))[1]


@pytest.mark.django_db
class TestCommand:
    def test_text_report_lists_differences_and_zero_writes(self, identical):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.382"))
        out = StringIO()
        call_command("shadow_compare_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="30,45", stdout=out)
        text = out.getvalue()
        assert "READ ONLY" in text
        assert "UNEXPLAINED_DIFFERENCE" in text
        assert "Writes performed: 0" in text

    def test_json_and_fail_on_unexplained(self, identical, tmp_path):
        out = StringIO()
        call_command("shadow_compare_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="45",
                     format="json", stdout=out, fail_on_unexplained=True)
        payload = json.loads(out.getvalue())
        assert payload["writes_performed"] == 0
        assert payload["counts"]["UNEXPLAINED_DIFFERENCE"] == 0
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.382"))
        with pytest.raises(CommandError, match="Unexplained"):
            call_command("shadow_compare_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="45",
                         stdout=StringIO(), fail_on_unexplained=True)

    def test_bad_arguments(self, identical, tmp_path):
        with pytest.raises(CommandError, match="--lane"):
            call_command("shadow_compare_rate_matrix", lane=["BNEPOM"])
        with pytest.raises(CommandError, match="--date"):
            call_command("shadow_compare_rate_matrix", date="15-06-2030")
        with pytest.raises(CommandError, match="--weights"):
            call_command("shadow_compare_rate_matrix", weights="a,b")
        with pytest.raises(CommandError, match="not found"):
            call_command("shadow_compare_rate_matrix", explained=str(tmp_path / "absent.json"))

    def test_explained_registry_file(self, identical, tmp_path):
        ImportCOGS.objects.filter(product_code__code=SCREEN).update(rate_per_kg=D("0.382"))
        path = tmp_path / "explained.json"
        path.write_text(json.dumps({"registry_version": 1, "entries": [{
            "lane": LANE, "side": "BUY", "product_code": SCREEN, "aspect": "unit_rate", "legacy": "0.382",
            "matrix": "0.38", "reason": "Synthetic reason.", "evidence": "SYNTHETIC",
        }]}), encoding="utf-8")
        out = StringIO()
        call_command("shadow_compare_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="45",
                     explained=str(path), format="json", stdout=out, fail_on_unexplained=True)
        payload = json.loads(out.getvalue())
        assert payload["counts"]["EXPECTED_DIFFERENCE"] == 1
        assert payload["counts"]["UNEXPLAINED_DIFFERENCE"] == 0
        assert shadow.EXPECTED_DIFFERENCE == "EXPECTED_DIFFERENCE"
