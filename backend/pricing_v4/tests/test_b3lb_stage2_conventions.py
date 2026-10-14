"""Pilot Gate B3L-B: the Stage-2 shadow under the approved calculation conventions.

Synthetic data only (reuses the B3K synthetic world). Nothing here is an approved value.
"""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from core.fx_market_models import FxMarketRate
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.services.rate_matrix_stage2_shadow import BLOCKED, MATCH, UNEXPLAINED_DIFFERENCE
from pricing_v4.tests.test_rate_matrix_stage2_shadow import (  # noqa: F401  (world is a fixture)
    TODAY,
    one,
    pick,
    run,
    scenario_key,
    snapshot,
    world,
)

APPROVED = dict(
    margin_percent=D("16.67"), margin_method="TARGET_GROSS_MARGIN",
    caf_method="TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
    fx_side_convention="FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL", fx_max_age_days=5, fx_primary_source="SYNTHETIC",
    fx_fallback_source="MANUAL",
)


@pytest.fixture
def approved(world):  # noqa: F811
    CommercialTermsPolicy.objects.update(**APPROVED)
    return world


@pytest.mark.django_db
class TestStage2UnderApprovedConventions:
    def test_matrix_and_legacy_agree_under_the_approved_conventions(self, approved):
        report = run(terms=("COLLECT", "PREPAID"), scopes=("A2D", "D2D"),
                     weights=tuple(D(w) for w in (30, 100, 1000)))
        counts = report.counts()
        assert counts[UNEXPLAINED_DIFFERENCE] == 0
        assert counts[BLOCKED] == 0, {r.reason for r in report.records if r.classification == BLOCKED}
        assert counts[MATCH] > 50

    def test_conversion_is_tt_buy_with_caf_rate_reduction_then_target_margin(self, approved):
        sell = one(run(weights=(D(100),)), scenario=scenario_key("100"), product_code="IMP-SYN-FRT",
                   aspect="sell_amount")
        assert sell.classification == MATCH
        assert D(sell.shadow) > 0
        # cost AUD x TT BUY / 0.95 (CAF reduces the published rate), then / (1 - 0.1667)
        cost = one(run(weights=(D(100),)), scenario=scenario_key("100"), product_code="IMP-SYN-FRT",
                   aspect="cost_amount")
        assert cost.classification == MATCH

    def test_provenance_reports_side_source_role_and_age(self, approved):
        report = run(weights=(D(100),))
        leg = report.fx_provenance[0]
        assert (leg["pair"], leg["side"], leg["source"], leg["source_role"]) == (
            "AUD/PGK", "TT_BUY", "SYNTHETIC", "PRIMARY")
        assert leg["age_days"] == 5 and leg["max_age_days"] == 5
        assert report.policy["caf_method"] == "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT"
        assert report.policy["fx_side_convention"] == "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL"

    def test_a_rate_one_day_past_the_policy_limit_blocks_conversion_scenarios(self, approved):
        FxMarketRate.objects.update(effective_date=TODAY - timedelta(days=6))
        report = run(weights=(D(100),))
        blocked = one(report, scenario=scenario_key("100"), aspect="scenario")
        assert blocked.classification == BLOCKED
        assert "StaleFxMarketRateError" in blocked.reason

    def test_no_conversion_scenarios_price_without_any_fx(self, approved):
        FxMarketRate.objects.all().delete()
        report = run(weights=(D(100),), terms=("COLLECT", "PREPAID"), scopes=("A2D", "D2D"))
        blocked = {r.scenario for r in pick(report, aspect="scenario") if r.classification == BLOCKED}
        # Only the scenario that genuinely converts AUD cost to a PGK quote needs FX.
        assert blocked == {scenario_key("100", "COLLECT", "D2D", "PGK")}
        for key in (scenario_key("100", "PREPAID", "A2D", "AUD"), scenario_key("100", "PREPAID", "D2D", "AUD"),
                    scenario_key("100", "COLLECT", "A2D", "PGK")):
            priced = pick(report, scenario=key)
            assert priced and all(r.classification != BLOCKED for r in priced)
        assert report.fx_provenance == []  # nothing converted, so nothing to report

    def test_the_run_writes_nothing(self, approved):
        before = snapshot()
        run(weights=(D(100),))
        assert snapshot() == before
