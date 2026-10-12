"""Pilot Gate B3L-F: Stage-2 attribution of an approved native difference to a converted fallback line.

Legacy PREPAID AUD can select a PGK ANY row and convert it. Stage-1 compares native rows in the context's own
currency, so it records the approved presence difference under COLLECT/PGK only. These tests prove Stage-2
inherits that approved fact for the converted line only when every link is proven, and never otherwise.

All values are synthetic test data. Nothing here is a real tariff, rate, FX value or approval.
"""

# ruff: noqa: F811  (the shared `world` fixture is imported and requested by name)

from datetime import date
from decimal import Decimal as D

import pytest

from core.fx_market_models import (
    FxMarketRate,  # noqa: F401  (fixture world creates FX rows)
)
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import LocalSellRate
from pricing_v4.services.rate_matrix_shadow import Record as Stage1Record
from pricing_v4.services.rate_matrix_stage2_shadow import (
    EXPECTED_DIFFERENCE,
    MATCH,
    UNEXPLAINED_DIFFERENCE,
    Line,
    Priced,
    Scenario,
    SourceRow,
    _Stage2,
)
from pricing_v4.tests.test_rate_matrix_stage2_shadow import (  # noqa: F401  (fixtures and helpers)
    LANE,
    LANE_NAME,
    TODAY,
    _entry,
    _legacy,
    one,
    pick,
    run,
    scenario_key,
    world,
)

LOAD, OTHER = "IMP-SYN-LOADING-DEST", "IMP-SYN-OTHER-DEST"
# The charge is absent on the Rate Matrix side, so it is reported as a presence difference.
ASPECTS = ("presence",)
TOTALS = ("total_sell_pgk", "total_gst", "total_sell_incl_gst")


def _pgk_only_charge(world, pk, code, *, any_amount="150", collect_amount="150"):
    product = _legacy(pk, code, "HANDLING")
    CommercialProductCode.objects.create(
        code=code, name=f"Synthetic {code}", category="DESTINATION", sub_category="", gst_treatment="STANDARD",
        charge_basis_default="FLAT", is_active=True, legacy_product_code=product,
    )
    for term, amount in (("ANY", any_amount), ("COLLECT", collect_amount)):
        LocalSellRate.objects.create(
            product_code=product, location="XPM", direction="IMPORT", payment_term=term, currency="PGK",
            rate_type="FIXED", amount=D(amount), valid_from=date(2030, 1, 1), valid_until=date(2030, 12, 31),
        )
    return product


@pytest.fixture
def loading(world):
    """A destination charge with PGK rows only (ANY and COLLECT) and no Rate Matrix tariff."""
    return _pgk_only_charge(world, 98810, LOAD)


APPROVED = [_entry("*-XPM", "SELL", LOAD, "presence", "present", "absent")]


def both_terms(**kwargs):
    kwargs.setdefault("weights", (D(100),))
    kwargs.setdefault("terms", ("COLLECT", "PREPAID"))
    kwargs.setdefault("scopes", ("D2D",))
    return run(**kwargs)


PREPAID = scenario_key("100", "PREPAID", "D2D", "AUD")
COLLECT = scenario_key("100", "COLLECT", "D2D", "PGK")


@pytest.mark.django_db
class TestRealisticConvertedFallback:
    def test_prepaid_aud_converted_line_inherits_the_approved_presence_difference(self, world, loading):
        report = both_terms(stage1_registry=APPROVED)
        for aspect in ASPECTS:
            line = one(report, scenario=PREPAID, product_code=LOAD, aspect=aspect)
            assert line.classification == EXPECTED_DIFFERENCE, line.reason
        reason = one(report, scenario=PREPAID, product_code=LOAD, aspect="presence").reason
        assert "converted PGK fallback row LocalSellRate#" in reason
        assert "COLLECT/PGK" in reason
        # Provenance of the native source is explicit: the legacy source row is the ANY row, in PGK.
        assert str(LocalSellRate.objects.get(product_code=loading, payment_term="ANY").pk) in reason

    def test_totals_become_expected_because_the_counterfactual_reproduces_them(self, world, loading):
        report = both_terms(stage1_registry=APPROVED)
        totals = [one(report, scenario=PREPAID, product_code="TOTAL", aspect=a) for a in TOTALS]
        assert all(t.classification in (EXPECTED_DIFFERENCE, MATCH) for t in totals), [t.reason for t in totals]
        assert {t.classification for t in totals} == {EXPECTED_DIFFERENCE}
        assert not [r for r in report.records if r.classification == UNEXPLAINED_DIFFERENCE]

    def test_collect_pgk_behaviour_is_unchanged(self, world, loading):
        with_prepaid = both_terms(stage1_registry=APPROVED)
        collect_only = both_terms(stage1_registry=APPROVED, terms=("COLLECT",))
        for aspect in ASPECTS + TOTALS:
            product = "TOTAL" if aspect in TOTALS else LOAD
            a = one(with_prepaid, scenario=COLLECT, product_code=product, aspect=aspect)
            b = one(collect_only, scenario=COLLECT, product_code=product, aspect=aspect)
            assert (a.classification, a.legacy, a.shadow, a.reason) == (
                b.classification, b.legacy, b.shadow, b.reason)
        collect_line = one(with_prepaid, scenario=COLLECT, product_code=LOAD, aspect="presence")
        assert collect_line.classification == EXPECTED_DIFFERENCE
        assert "converted" not in collect_line.reason  # approved natively, no inheritance needed

    def test_without_the_approved_registry_entry_nothing_is_inherited(self, world, loading):
        report = both_terms(stage1_registry=[])
        for scenario in (COLLECT, PREPAID):
            assert one(report, scenario=scenario, product_code=LOAD, aspect="presence").classification == (
                UNEXPLAINED_DIFFERENCE)

    def test_an_unrelated_product_cannot_inherit_the_evidence(self, world, loading):
        _pgk_only_charge(world, 98811, OTHER)  # same shape, same amounts, but no approval of its own
        report = both_terms(stage1_registry=APPROVED)
        assert one(report, scenario=PREPAID, product_code=LOAD, aspect="presence").classification == (
            EXPECTED_DIFFERENCE)
        other = one(report, scenario=PREPAID, product_code=OTHER, aspect="presence")
        assert other.classification == UNEXPLAINED_DIFFERENCE
        total = one(report, scenario=PREPAID, product_code="TOTAL", aspect="total_sell_incl_gst")
        assert total.classification == UNEXPLAINED_DIFFERENCE  # a contributing difference is unexplained

    def test_a_different_underlying_row_cannot_inherit_the_evidence(self, world):
        # The ANY row the PREPAID quote converts holds 140; the COLLECT row Stage-1 evidenced holds 150.
        _pgk_only_charge(world, 98810, LOAD, any_amount="140", collect_amount="150")
        report = both_terms(stage1_registry=APPROVED)
        line = one(report, scenario=PREPAID, product_code=LOAD, aspect="presence")
        assert line.classification == UNEXPLAINED_DIFFERENCE
        total = one(report, scenario=PREPAID, product_code="TOTAL", aspect="total_sell_incl_gst")
        assert total.classification == UNEXPLAINED_DIFFERENCE
        # COLLECT still resolves its own exact row and stays explained.
        assert one(report, scenario=COLLECT, product_code=LOAD, aspect="presence").classification == (
            EXPECTED_DIFFERENCE)

    def test_the_run_remains_read_only(self, world, loading):
        before = list(LocalSellRate.objects.order_by("id").values())
        both_terms(stage1_registry=APPROVED)
        assert list(LocalSellRate.objects.order_by("id").values()) == before


# --------------------------------------------------------------------------- unit checks of every link


def _line(*, converted=True, sell_currency="AUD", missing=False):
    return Line(
        product_code=LOAD, leg="DESTINATION", sell_amount=D("50.65"), sell_currency=sell_currency,
        cost_amount=D(0), cost_currency="PGK", gst_amount=D("5.07"), gst_category="service_in_PNG",
        gst_rate=D("0.10"), sell_incl_gst=D("55.72"), fx_applied=converted, caf_applied=converted,
        margin_applied=False, is_rate_missing=missing,
    )


FACTS = ("synthetic-native-facts",)


def _source(row_id=84, currency="PGK", facts=FACTS):
    return SourceRow(row_id, currency, "ANY", facts)


def _conversion(**changes):
    base = {"product_code": LOAD, "role": "SELL", "from_currency": "PGK", "to_currency": "AUD"}
    return {**base, **changes}


def _record(aspect="presence", legacy="present", matrix="absent", evidence="B3E decision 8", context="COLLECT/PGK"):
    return Stage1Record("*-XPM", "SELL", LOAD, aspect, "LEGACY_ONLY", legacy, matrix, context, "", evidence)


class Harness:
    def __init__(self, **overrides):
        self.scenario = overrides.pop("scenario", Scenario(LANE_NAME, D(100), "PREPAID", "D2D", "AUD"))
        self.stage2 = _Stage2(TODAY, (LANE,), (D(100),), ("PREPAID",), ("D2D",), [], None, "default")
        self.stage2._stage1_rows = overrides.pop(
            "stage1_rows", {("SELL", LOAD, "COLLECT/PGK"): (166, FACTS, "PGK")}
        )
        sources = overrides.pop("sources", (_source(),))
        conversions = overrides.pop("conversions", [_conversion()])
        line = overrides.pop("line", _line())
        self.legacy = Priced({LOAD: line}, {}, conversions, {LOAD: sources} if sources else {})
        self.shadow = Priced(overrides.pop("shadow_lines", {}), {})
        self.index = overrides.pop("index", {("SELL", LOAD, "COLLECT/PGK"): [_record()]})
        assert not overrides, overrides

    def evidence(self):
        return self.stage2._converted_fallback_evidence(
            self.scenario, LOAD, self.legacy, self.shadow, self.index
        )


class TestEveryLinkIsRequired:
    def test_all_links_proven_inherits_presence_only(self):
        explained, unexplained = Harness().evidence()
        assert len(explained) == 1 and explained[0].startswith("presence (converted PGK fallback row")
        assert unexplained == []

    def test_ambiguous_lineage_two_source_rows_inherits_nothing(self):
        assert Harness(sources=(_source(84), _source(85))).evidence() == ([], [])

    def test_missing_source_row_inherits_nothing(self):
        assert Harness(sources=()).evidence() == ([], [])

    def test_no_conversion_lineage_inherits_nothing(self):
        assert Harness(line=_line(converted=False)).evidence() == ([], [])

    def test_a_line_already_in_the_source_currency_inherits_nothing(self):
        assert Harness(line=_line(sell_currency="PGK"), scenario=Scenario(LANE_NAME, D(100), "COLLECT", "D2D", "PGK")
                       ).evidence() == ([], [])

    def test_conversion_evidence_that_disagrees_inherits_nothing(self):
        assert Harness(conversions=[_conversion(from_currency="USD")]).evidence() == ([], [])
        assert Harness(conversions=[_conversion(role="COST")]).evidence() == ([], [])

    def test_the_rate_matrix_side_pricing_the_charge_inherits_nothing(self):
        assert Harness(shadow_lines={LOAD: _line(converted=True)}).evidence() == ([], [])

    def test_a_missing_rate_placeholder_on_the_shadow_side_is_the_absent_case(self):
        explained, _ = Harness(shadow_lines={LOAD: _line(missing=True)}).evidence()
        assert explained

    def test_a_different_source_row_inherits_nothing(self):
        assert Harness(sources=(_source(facts=("other",)),)).evidence() == ([], [])

    def test_stage1_row_in_another_currency_inherits_nothing(self):
        assert Harness(stage1_rows={("SELL", LOAD, "COLLECT/PGK"): (166, FACTS, "USD")}).evidence() == ([], [])

    def test_another_product_or_side_inherits_nothing(self):
        rows = {("SELL", OTHER, "COLLECT/PGK"): (166, FACTS, "PGK"), ("BUY", LOAD, "COLLECT/PGK"): (1, FACTS, "PGK")}
        assert Harness(stage1_rows=rows).evidence() == ([], [])

    def test_unapproved_evidence_inherits_nothing(self):
        assert Harness(index={("SELL", LOAD, "COLLECT/PGK"): [_record(evidence="")]}).evidence() == ([], [])

    def test_a_value_difference_alongside_presence_inherits_nothing(self):
        records = [_record(), _record(aspect="unit_rate", legacy="150", matrix="165")]
        assert Harness(index={("SELL", LOAD, "COLLECT/PGK"): records}).evidence() == ([], [])

    def test_a_non_absent_matrix_value_inherits_nothing(self):
        assert Harness(index={("SELL", LOAD, "COLLECT/PGK"): [_record(matrix="present")]}).evidence() == ([], [])

    def test_evidence_for_another_weight_inherits_nothing(self):
        records = [_record(aspect="rate@45kg", legacy="150", matrix="165")]  # scenario weight is 100 kg
        assert Harness(index={("SELL", LOAD, "COLLECT/PGK"): records}).evidence() == ([], [])

    def test_no_stage1_record_at_all_inherits_nothing(self):
        assert Harness(index={}).evidence() == ([], [])


def test_pick_helper_is_importable():
    assert pick  # keeps the shared test helper import honest
