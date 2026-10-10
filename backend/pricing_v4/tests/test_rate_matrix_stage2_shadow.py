"""Pilot Gate B3K: Stage-2 read-only commercial shadow pricing.

Every value here is synthetic test data, including the FX rates and the commercial policy. Nothing
here is a real tariff, rate, CAF, margin, GST, or FX value and none is approved for any purpose.
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

from core.fx_market_models import FxMarketRate
from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialProductCode, CommercialTermsPolicy
from pricing_v4.engine.import_engine import ImportPricingEngine
from pricing_v4.models import Agent, ImportCOGS, LocalSellRate, ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_stage2_shadow import (
    BLOCKED,
    EXPECTED_DIFFERENCE,
    MATCH,
    UNEXPLAINED_DIFFERENCE,
    MatrixShadowImportEngine,
    run_stage2,
)

TODAY = date(2030, 6, 15)
FRT, PICK, FSC = "IMP-SYN-FRT", "IMP-SYN-PICKUP-ORIGIN", "IMP-SYN-FSC-ORIGIN"
DOC, ZERO, TERM = "IMP-SYN-DOC-DEST", "IMP-SYN-ZERO-DEST", "IMP-SYN-TERM-DEST"
LANE = ("XAA", "XPM")
LANE_NAME = "XAA-XPM"
FRT_BREAKS = [{"min_kg": 0, "rate": "7.50"}, {"min_kg": 45, "rate": "7.35"}, {"min_kg": 100, "rate": "7.00"},
              {"min_kg": 250, "rate": "6.75"}, {"min_kg": 500, "rate": "6.45"}, {"min_kg": 1000, "rate": "6.10"}]
PICK_BREAKS = [{"min_kg": 0, "rate": "0.26"}, {"min_kg": 1000, "rate": "0.21"}]


def _legacy(pk, code, category, unit="SHIPMENT", gst="STANDARD", **extra):
    return ProductCode.objects.create(
        id=pk, code=code, description=f"Synthetic {code}", domain="IMPORT", category=category,
        is_gst_applicable=gst == "STANDARD", gst_rate="0.1000" if gst == "STANDARD" else "0.0000",
        gst_treatment=gst, gl_revenue_code="4000", gl_cost_code="5000", default_unit=unit, **extra,
    )


@pytest.fixture
def world(db):
    for code in ("PGK", "AUD"):
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
        FRT: _legacy(98801, FRT, "FREIGHT", "KG"),
        PICK: _legacy(98802, PICK, "CARTAGE", "KG"),
        DOC: _legacy(98804, DOC, "DOCUMENTATION"),
        ZERO: _legacy(98805, ZERO, "DOCUMENTATION", gst="ZERO_RATED"),
        TERM: _legacy(98806, TERM, "HANDLING"),
    }
    products[FSC] = _legacy(98803, FSC, "SURCHARGE", "PERCENT", percent_of_product_code=products[PICK])
    mirrors = {}
    for code, category, basis in (
        (FRT, "FREIGHT", "TIERED_WEIGHT"), (PICK, "ORIGIN", "TIERED_WEIGHT"), (FSC, "ORIGIN", "PERCENTAGE"),
        (DOC, "DESTINATION", "FLAT"), (ZERO, "DESTINATION", "FLAT"), (TERM, "DESTINATION", "FLAT"),
    ):
        mirrors[code] = CommercialProductCode.objects.create(
            code=code, name=f"Synthetic {code}", category=category, sub_category="",
            gst_treatment=products[code].gst_treatment, charge_basis_default=basis, is_active=True,
            legacy_product_code=products[code],
        )
    user = get_user_model().objects.create_user(username="synthetic-stage2", password="x")
    CommercialTermsPolicy.objects.all().delete()  # a migration seeds a launch policy; tests state their own
    FxMarketRate.objects.all().delete()
    CommercialTermsPolicy.objects.create(
        policy_code="SYNTHETIC-POLICY", valid_from=date(2030, 1, 1), margin_percent=D("20.00"),
        margin_method="MARKUP_ON_COST", import_caf_percent=D("5.00"), gst_standard_percent=D("10.00"),
    )
    FxMarketRate.objects.create(
        base_currency="AUD", quote_currency="PGK", effective_date=date(2030, 6, 10), tt_buy_rate=D("2.60"),
        tt_sell_rate=D("2.70"), mid_rate=D("2.65"), source="SYNTHETIC",
    )
    world = {"places": places, "party": party, "agent": agent, "products": products, "mirrors": mirrors, "user": user}
    _matrix(world)
    _legacy_rows(world)
    return world


def _sheet(world, name, rate_type, currency, *, supplier=False):
    return RateSheet.objects.create(
        name=name, version=1, rate_type=rate_type, transport_mode="AIR", currency_code=currency,
        valid_from=date(2030, 1, 1), valid_until=date(2030, 12, 31), is_active=True,
        source_reference="SYNTHETIC-TEST", carrier=world["party"] if supplier else None, created_by=world["user"],
    )


def _line(world, sheet, code, basis, *, origin=None, destination=None, tiers=(), pct_basis=None, **amounts):
    line = RateLine.objects.create(
        sheet=sheet, product_code=world["mirrors"][code], rate_basis=basis,
        percentage_basis_product_code=world["mirrors"][pct_basis] if pct_basis else None, **amounts,
    )
    RateApplicability.objects.create(
        rate_line=line, direction="IMPORT",
        origin=world["places"][origin] if origin else None,
        destination=world["places"][destination] if destination else None,
    )
    for lower, upper, rate in tiers:
        RateTier.objects.create(
            rate_line=line, min_quantity=D(lower), max_quantity=None if upper is None else D(upper), unit_rate=D(rate)
        )
    return line


def _matrix(world):
    buy = _sheet(world, "Synthetic BUY", "BUY", "AUD", supplier=True)
    _line(world, buy, FRT, "TIERED_WEIGHT", origin="XAA", destination="XPM", min_charge=D(350),
          tiers=(("0", "45", "7.50"), ("45", "100", "7.35"), ("100", "250", "7.00"), ("250", "500", "6.75"),
                 ("500", "1000", "6.45"), ("1000", None, "6.10")))
    _line(world, buy, PICK, "TIERED_WEIGHT", origin="XAA", min_charge=D(85),
          tiers=(("0", "1000", "0.26"), ("1000", None, "0.21")))
    _line(world, buy, FSC, "PERCENTAGE", origin="XAA", percentage_rate=D(20), pct_basis=PICK)
    for currency, doc, term in (("PGK", "165", "165"), ("AUD", "80", "60")):
        sell = _sheet(world, f"Synthetic SELL {currency}", "SELL", currency)
        _line(world, sell, DOC, "FLAT", destination="XPM", unit_rate=D(doc))
        _line(world, sell, ZERO, "FLAT", destination="XPM", unit_rate=D(100))
        _line(world, sell, TERM, "FLAT", destination="XPM", unit_rate=D(term))


def _legacy_rows(world):
    products, agent = world["products"], world["agent"]
    base = {"origin_airport": "XAA", "currency": "AUD", "agent": agent, "valid_from": date(2030, 1, 1),
            "valid_until": date(2030, 12, 31)}
    ImportCOGS.objects.create(product_code=products[FRT], destination_airport="XPM", scope="LANE",
                              min_charge=D(350), weight_breaks=FRT_BREAKS, **base)
    ImportCOGS.objects.create(product_code=products[PICK], scope="ORIGIN", rate_per_kg=D("0.26"),
                              min_charge=D(85), weight_breaks=PICK_BREAKS, **base)
    ImportCOGS.objects.create(product_code=products[FSC], scope="ORIGIN", percent_rate=D(20), **base)
    for currency, doc, term in (("PGK", "165", "165"), ("AUD", "80", "60")):
        for code, amount in ((DOC, doc), (ZERO, "100"), (TERM, term)):
            LocalSellRate.objects.create(
                product_code=products[code], location="XPM", direction="IMPORT", payment_term="ANY",
                currency=currency, rate_type="FIXED", amount=D(amount), valid_from=date(2030, 1, 1),
                valid_until=date(2030, 12, 31),
            )


def run(**kwargs):
    kwargs.setdefault("lanes", (LANE,))
    kwargs.setdefault("weights", (D(30), D(100), D(1000)))
    kwargs.setdefault("terms", ("COLLECT",))
    kwargs.setdefault("scopes", ("D2D",))
    return run_stage2(quote_date=TODAY, **kwargs)


def pick(report, **match):
    return [r for r in report.records if all(getattr(r, k) == v for k, v in match.items())]


def one(report, **match):
    found = pick(report, **match)
    assert len(found) == 1, (match, [r.as_dict() for r in found])
    return found[0]


def scenario_key(weight, term="COLLECT", scope="D2D", currency="PGK"):
    return f"{weight}kg|{term}|{scope}|{currency}"


def snapshot():
    return {
        "matrix": [m.objects.count() for m in (RateSheet, RateLine, RateApplicability, RateTier)],
        "legacy": list(ImportCOGS.objects.order_by("id").values()),
        "sell": list(LocalSellRate.objects.order_by("id").values()),
        "fx": list(FxMarketRate.objects.order_by("id").values()),
        "policy": list(CommercialTermsPolicy.objects.values()),
    }


# --------------------------------------------------------------------------- identical data


@pytest.mark.django_db
class TestIdenticalData:
    def test_every_charge_and_total_matches_across_scopes_terms_and_weights(self, world):
        report = run(terms=("COLLECT", "PREPAID"), scopes=("A2D", "D2D"),
                     weights=tuple(D(w) for w in (30, 45, 100, 250, 500, 999, 1000, 1001)))
        counts = report.counts()
        assert counts[UNEXPLAINED_DIFFERENCE] == counts[BLOCKED] == counts[EXPECTED_DIFFERENCE] == 0, {
            r.reason for r in report.records if r.classification != MATCH}
        assert counts[MATCH] > 100
        assert len({r.scenario for r in report.records}) == 8 * 2 * 2

    def test_commercial_rules_are_the_unmodified_production_engine(self, world):
        report = run()
        sell = one(report, scenario=scenario_key("100"), product_code=FRT, aspect="sell_amount")
        # Cost-plus: AUD cost converted through FX and CAF, then margin. The shadow and production
        # engines agree because they are the same code; the amount is not a literal here.
        assert sell.classification == MATCH
        assert sell.currency == "PGK"
        assert "FX" in sell.stage and "CAF" in sell.stage and "margin" in sell.stage
        assert D(sell.shadow) > D(700)

    def test_shadow_engine_overrides_only_rate_lookups(self):
        own = {name for name, value in vars(MatrixShadowImportEngine).items() if callable(value)}
        assert own == {"__init__", "_get_cogs", "_get_local_cogs", "_get_sell_rate",
                       "_get_destination_sell_rate", "_calculate_cogs_amount"}
        for name in ("_apply_margin", "_convert_fcy_to_pgk", "_convert_pgk_to_fcy", "_calculate_charge_line",
                     "_calculate_sell_amount", "calculate_quote"):
            assert getattr(MatrixShadowImportEngine, name) is getattr(ImportPricingEngine, name)


# --------------------------------------------------------------------------- pickup boundary


@pytest.mark.django_db
class TestPickupBoundary:
    @pytest.mark.parametrize(
        ("weight", "native_aud"),
        [("999", "259.74"), ("1000", "210.00"), ("1001", "210.21")],
    )
    def test_the_021_rate_starts_at_exactly_1000_kg(self, world, weight, native_aud):
        report = run(weights=(D(weight),), scopes=("D2D",))
        cost = one(report, scenario=scenario_key(weight), product_code=PICK, aspect="cost_amount")
        assert cost.classification == MATCH
        assert (cost.legacy, cost.shadow, cost.currency) == (native_aud, native_aud, "AUD")
        assert one(report, scenario=scenario_key(weight), product_code=PICK, aspect="sell_amount").classification == MATCH

    def test_a_legacy_row_without_the_1000_kg_break_is_flagged_at_1000_and_not_at_999(self, world):
        ImportCOGS.objects.filter(product_code__code=PICK).update(weight_breaks=None)
        report = run(weights=(D(999), D(1000), D(1001)))
        assert one(report, scenario=scenario_key("999"), product_code=PICK, aspect="cost_amount").classification == MATCH
        for weight in ("1000", "1001"):
            diff = one(report, scenario=scenario_key(weight), product_code=PICK, aspect="cost_amount")
            assert diff.classification == UNEXPLAINED_DIFFERENCE
        assert one(report, scenario=scenario_key("1000"), product_code=PICK, aspect="cost_amount").shadow == "210.00"
        assert one(report, scenario=scenario_key("1000"), product_code=PICK, aspect="cost_amount").legacy == "260.00"


# --------------------------------------------------------------------------- minimums, surcharges, GST


@pytest.mark.django_db
class TestCommercialRules:
    def test_minimum_charge_applies_below_the_break_even_weight(self, world):
        report = run(weights=(D(30), D(100)))
        low = one(report, scenario=scenario_key("30"), product_code=FRT, aspect="cost_amount")
        high = one(report, scenario=scenario_key("100"), product_code=FRT, aspect="cost_amount")
        assert (low.shadow, low.classification) == ("350.00", MATCH)  # 30 kg x 7.50 = 225 < minimum
        assert (high.shadow, high.classification) == ("700.00", MATCH)  # 100 kg x 7.00

    def test_percentage_surcharge_follows_its_basis(self, world):
        report = run(weights=(D(100),))
        pickup = D(one(report, scenario=scenario_key("100"), product_code=PICK, aspect="cost_amount").shadow)
        fsc = one(report, scenario=scenario_key("100"), product_code=FSC, aspect="cost_amount")
        assert pickup == D("85.00")  # 100 kg x 0.26 = 26 < minimum 85
        assert D(fsc.shadow) == D("17.00")  # 20% of the pickup
        assert fsc.classification == MATCH

    def test_percentage_basis_disagreement_blocks(self, world):
        RateLine.objects.filter(product_code__code=FSC).update(
            percentage_basis_product_code=world["mirrors"][FRT]
        )
        report = run(weights=(D(100),))
        blocked = one(report, scenario=scenario_key("100"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "PERCENTAGE_BASIS_MISMATCH" in blocked.reason

    def test_standard_and_zero_rated_gst_follow_the_production_classification(self, world):
        report = run(weights=(D(100),), scopes=("A2D",))
        std = one(report, scenario=scenario_key("100", scope="A2D"), product_code=DOC, aspect="gst_amount")
        zero = one(report, scenario=scenario_key("100", scope="A2D"), product_code=ZERO, aspect="gst_amount")
        assert (std.legacy, std.shadow, std.classification) == ("16.50", "16.50", MATCH)  # 10% of 165.00
        assert (zero.legacy, zero.shadow, zero.classification) == ("0.00", "0.00", MATCH)
        assert "GST classification" in std.stage

    def test_gst_treatment_disagreement_between_mirror_and_legacy_blocks(self, world):
        CommercialProductCode.objects.filter(code=DOC).update(gst_treatment="ZERO_RATED")
        report = run(weights=(D(100),), scopes=("A2D",))
        blocked = one(report, scenario=scenario_key("100", scope="A2D"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "GST_TREATMENT_MISMATCH" in blocked.reason

# --------------------------------------------------------------------------- terminal fee and explanation


@pytest.mark.django_db
class TestTerminalFeeAndExplanations:
    @pytest.fixture(autouse=True)
    def _no_legacy_terminal_row(self, world):
        # IMP-TERM-DEST is a new ProductCode with no legacy rate row.
        LocalSellRate.objects.filter(product_code__code=TERM).delete()

    def test_matrix_only_terminal_fee_is_unexplained_by_default(self, world):
        report = run(weights=(D(100),), scopes=("A2D",))
        fee = one(report, scenario=scenario_key("100", scope="A2D"), product_code=TERM, aspect="presence")
        assert fee.classification == UNEXPLAINED_DIFFERENCE
        assert (fee.legacy, fee.shadow) == ("absent", "present")
        totals = one(report, scenario=scenario_key("100", scope="A2D"), product_code="TOTAL", aspect="total_sell_pgk")
        assert totals.classification == UNEXPLAINED_DIFFERENCE
        assert D(totals.shadow) - D(totals.legacy) == D("165.00")

    def test_stage1_registry_turns_it_into_an_expected_difference_with_provenance(self, world):
        registry = [{
            "lane": "*-XPM", "side": "SELL", "product_code": TERM, "aspect": "presence", "legacy": "absent",
            "matrix": "present", "reason": "Synthetic new ProductCode.", "evidence": "SYNTHETIC-EVIDENCE",
        }]
        report = run(weights=(D(100),), scopes=("A2D",), stage1_registry=registry)
        fee = one(report, scenario=scenario_key("100", scope="A2D"), product_code=TERM, aspect="presence")
        assert fee.classification == EXPECTED_DIFFERENCE
        assert fee.currency == "PGK"
        assert "Stage-1" in fee.reason
        assert "SYNTHETIC-POLICY" in fee.provenance and "NOT APPROVED FOR CUTOVER" in fee.provenance
        for aspect in ("total_sell_pgk", "total_gst", "total_sell_incl_gst"):
            total = one(report, scenario=scenario_key("100", scope="A2D"), product_code="TOTAL", aspect=aspect)
            assert total.classification == EXPECTED_DIFFERENCE

    def test_a_rate_difference_with_matching_native_facts_is_unexplained(self, world):
        # Same stored value but a different downstream result cannot be explained by Stage-1.
        LocalSellRate.objects.filter(product_code__code=DOC, currency="PGK").update(amount=D(150))
        report = run(weights=(D(100),), scopes=("A2D",))
        diff = one(report, scenario=scenario_key("100", scope="A2D"), product_code=DOC, aspect="sell_amount")
        assert diff.classification == UNEXPLAINED_DIFFERENCE
        assert (diff.legacy, diff.shadow) == ("150.00", "165.00")


# --------------------------------------------------------------------------- fail closed


@pytest.mark.django_db
class TestFailClosed:
    def test_missing_fx_blocks_conversion_scenarios_but_not_pgk_only_ones(self, world):
        FxMarketRate.objects.all().delete()
        report = run(weights=(D(100),), terms=("COLLECT", "PREPAID"), scopes=("A2D", "D2D"))
        by_key = {r.scenario: r for r in pick(report, aspect="scenario")}
        assert by_key[scenario_key("100", "COLLECT", "D2D", "PGK")].classification == BLOCKED
        assert by_key[scenario_key("100", "PREPAID", "A2D", "AUD")].classification == BLOCKED
        assert by_key[scenario_key("100", "PREPAID", "D2D", "AUD")].classification == BLOCKED
        assert "MissingFxMarketRateError" in by_key[scenario_key("100", "COLLECT", "D2D", "PGK")].reason
        # A2D COLLECT in PGK needs no FX at all and still prices.
        priced = pick(report, scenario=scenario_key("100", "COLLECT", "A2D", "PGK"))
        assert priced and all(r.classification != BLOCKED for r in priced)

    def test_stale_fx_blocks_only_when_a_limit_is_supplied(self, world):
        assert run(weights=(D(100),)).counts()[BLOCKED] == 0
        report = run(weights=(D(100),), max_fx_age_days=3)
        blocked = one(report, scenario=scenario_key("100"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "FX_STALE" in blocked.reason and "5 days old" in blocked.reason
        assert report.fx_provenance and report.fx_provenance[0]["status"].endswith("NOT APPROVED FOR CUTOVER.")

    def test_ambiguous_fx_sources_block(self, world):
        FxMarketRate.objects.create(
            base_currency="AUD", quote_currency="PGK", effective_date=date(2030, 6, 10), tt_buy_rate=D("2.50"),
            tt_sell_rate=D("2.60"), mid_rate=D("2.55"), source="SYNTHETIC-RIVAL",
        )
        blocked = one(run(weights=(D(100),)), scenario=scenario_key("100"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "Ambiguous" in blocked.reason or "ambiguous" in blocked.reason

    def test_missing_policy_blocks_everything(self, world):
        CommercialTermsPolicy.objects.all().delete()
        report = run()
        assert report.policy is None
        assert report.counts()[BLOCKED] == len(report.records) > 0
        assert all("POLICY_MISSING" in r.reason for r in report.records)

    def test_ambiguous_policy_blocks_even_though_production_would_pick_one(self, world):
        CommercialTermsPolicy.objects.create(
            policy_code="SYNTHETIC-POLICY-2", valid_from=date(2030, 3, 1), margin_percent=D("25.00"),
            margin_method="MARKUP_ON_COST", import_caf_percent=D("5.00"), gst_standard_percent=D("10.00"),
        )
        report = run()
        assert report.counts()[BLOCKED] == len(report.records) > 0
        assert all("POLICY_AMBIGUOUS" in r.reason for r in report.records)

    def test_incomplete_policy_blocks(self, world):
        CommercialTermsPolicy.objects.update(import_caf_percent=None)
        assert all("POLICY_INCOMPLETE" in r.reason for r in run().records)

    def test_inactive_or_expired_policy_does_not_count(self, world):
        CommercialTermsPolicy.objects.create(
            policy_code="SYNTHETIC-OLD", valid_from=date(2029, 1, 1), valid_until=date(2029, 12, 31),
            margin_percent=D("99.00"), margin_method="MARKUP_ON_COST", import_caf_percent=D("5.00"),
            gst_standard_percent=D("10.00"),
        )
        assert run().policy["policy_code"] == "SYNTHETIC-POLICY"

    def test_ambiguous_matrix_tariff_blocks_the_scenario(self, world):
        rival = _sheet(world, "Synthetic SELL PGK RIVAL", "SELL", "PGK")
        _line(world, rival, DOC, "FLAT", destination="XPM", unit_rate=D(999))
        blocked = one(run(weights=(D(100),), scopes=("A2D",)), scenario=scenario_key("100", scope="A2D"),
                      aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "RESOLVER_AMBIGUOUS" in blocked.reason

    def test_multiple_suppliers_block(self, world):
        other = PartyMaster.objects.create(legal_name="Synthetic Rival Agent", entity_type="COMPANY", country_code="ZZ")
        PartyRole.objects.create(party=other, role_type="AGENT")
        rival = RateSheet.objects.create(
            name="Synthetic BUY RIVAL", version=1, rate_type="BUY", transport_mode="AIR", currency_code="AUD",
            valid_from=date(2030, 1, 1), valid_until=date(2030, 12, 31), is_active=True,
            source_reference="SYNTHETIC-TEST", carrier=other, created_by=world["user"],
        )
        _line(world, rival, PICK, "FLAT", origin="XAA", unit_rate=D(1))
        blocked = one(run(weights=(D(100),)), scenario=scenario_key("100"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "SUPPLIER_NOT_SINGLE" in blocked.reason

    def test_synthetic_fx_provenance_is_reported_when_used(self, world):
        report = run(weights=(D(100),))
        assert [(i["pair"], i["source"], i["effective_date"]) for i in report.fx_provenance] == [
            ("AUD/PGK", "SYNTHETIC", "2030-06-10")
        ]


# --------------------------------------------------------------------------- safety and command


@pytest.mark.django_db
class TestSafety:
    def test_run_writes_nothing_and_leaves_policy_fx_tariffs_untouched(self, world):
        before = snapshot()
        with CaptureQueriesContext(connection) as queries:
            report = run(terms=("COLLECT", "PREPAID"), scopes=("A2D", "D2D"))
        assert snapshot() == before
        verbs = {q["sql"].lstrip().split(None, 1)[0].upper() for q in queries}
        assert not verbs & {"INSERT", "UPDATE", "DELETE"}, verbs
        assert report.as_dict()["writes_performed"] == 0

    def test_connection_is_writable_after_the_run(self, world):
        run()
        PartyMaster.objects.create(legal_name="Synthetic After", entity_type="COMPANY", country_code="ZZ")

    def test_report_states_policy_is_not_approved_for_cutover(self, world):
        report = run()
        assert report.policy["status"] == "LEGACY OBSERVED POLICY. NOT APPROVED FOR CUTOVER."
        assert report.policy["import_caf_percent"] == "5.00"
        assert "NOT APPROVED FOR CUTOVER" in report.render_text()

    def test_report_is_deterministic(self, world):
        assert run().render_json() == run().render_json()


@pytest.mark.django_db
class TestCommand:
    def test_text_and_json(self, world):
        out = StringIO()
        call_command("shadow_price_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="100",
                     terms="COLLECT", scopes="D2D", stdout=out)
        assert "Stage-2" in out.getvalue() and "Writes performed: 0" in out.getvalue()
        out = StringIO()
        call_command("shadow_price_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="100",
                     terms="COLLECT", scopes="D2D", format="json", stdout=out, fail_on_unexplained=True)
        payload = json.loads(out.getvalue())
        assert payload["writes_performed"] == 0
        assert payload["counts"]["UNEXPLAINED_DIFFERENCE"] == 0

    def test_fail_on_unexplained(self, world):
        LocalSellRate.objects.filter(product_code__code=DOC, currency="PGK").update(amount=D(150))
        with pytest.raises(CommandError, match="Unexplained"):
            call_command("shadow_price_rate_matrix", lane=["XAA-XPM"], date="2030-06-15", weights="100",
                         terms="COLLECT", scopes="A2D", stdout=StringIO(), fail_on_unexplained=True)

    def test_bad_arguments(self, world, tmp_path):
        for kwargs, message in (
            ({"lane": ["XAAXPM"]}, "--lane"), ({"date": "15/06/2030"}, "--date"), ({"weights": "x"}, "--weights"),
            ({"terms": "NET30"}, "--terms"), ({"scopes": "D2X"}, "--scopes"),
            ({"explained": str(tmp_path / "absent.json")}, "not found"),
        ):
            with pytest.raises(CommandError, match=message):
                call_command("shadow_price_rate_matrix", **kwargs)
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(CommandError, match="Registry errors"):
            call_command("shadow_price_rate_matrix", explained=str(bad))
