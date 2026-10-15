"""Pilot Gate B3M-E: BSP FX-side correction delivered as a new policy version.

The repository manifests are applied to the test database only. FX figures are the BSP AUD rates
published 2026-10-14 (TT Buy 0.3215, TT Sell 0.3065 AUD per PGK), stored inverted with the side kept.
"""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from core.fx_market_models import FxMarketRate
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.services import commercial_policy_loader as loader
from pricing_v4.services.commercial_policy import require_unique_commercial_terms_policy
from pricing_v4.services.fx_conventions import SupersededFxConventionError

MANIFESTS = Path(__file__).resolve().parents[1] / "policy_manifests"
OLD, NEW = "commercial-policy-2026-10-11.json", "commercial-policy-2026-10-14.json"


def apply_manifest(name, operator):
    text = (MANIFESTS / name).read_text(encoding="utf-8")
    plan = loader.plan_policy_text(text)
    assert plan.ready, plan.render_text()
    return loader.apply_policy_text(text, operator=operator, reviewed_sha256=plan.manifest_sha256)


@pytest.fixture
def policies(db):
    CommercialTermsPolicy.objects.all().delete()
    CommercialTermsPolicy.objects.create(
        policy_code="LAUNCH-POLICY-2026", valid_from=date(2026, 1, 1), margin_percent=D("20.00"),
        margin_method="MARKUP_ON_COST", import_caf_percent=D("5.00"), export_caf_percent=D("10.00"),
        gst_standard_percent=D("10.00"), is_active=True,
    )
    operator = get_user_model().objects.create_user(username="b3me-fx-operator", password="x")
    apply_manifest(OLD, operator)
    before = CommercialTermsPolicy.objects.filter(policy_code="COMMERCIAL-POLICY-2026-10-11").values().get()
    apply_manifest(NEW, operator)
    FxMarketRate.objects.all().delete()
    for day in (date(2026, 10, 12), date(2026, 10, 14)):
        FxMarketRate.objects.create(
            base_currency="AUD", quote_currency="PGK", effective_date=day, tt_buy_rate=D("3.11041991"),
            tt_sell_rate=D("3.26264274"), mid_rate=D("3.18653133"), source="bsp_html",
        )
    return before


def engine(quote_date):
    return ImportPricingEngine(
        quote_date=quote_date, origin="SYD", destination="POM", chargeable_weight_kg=D("100"),
        payment_term=PaymentTerm.COLLECT, service_scope=ServiceScope.D2D,
    )


@pytest.mark.django_db
class TestPolicyVersion:
    def test_new_version_carries_the_bsp_sides_and_supersedes_without_editing_history(self, policies):
        new = require_unique_commercial_terms_policy(date(2026, 10, 14))
        assert new.policy_code == "COMMERCIAL-POLICY-2026-10-14"
        assert (new.caf_method, new.fx_side_convention) == (
            "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT", "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL")
        assert (new.import_caf_percent, new.export_caf_percent, new.margin_percent) == (
            D("5.00"), D("10.00"), D("16.67"))
        old = CommercialTermsPolicy.objects.filter(policy_code="COMMERCIAL-POLICY-2026-10-11").values().get()
        assert old["valid_until"] == date(2026, 10, 13)
        assert {k: v for k, v in old.items() if k != "valid_until"} == {
            k: v for k, v in policies.items() if k != "valid_until"}
        assert (old["caf_method"], old["fx_side_convention"]) == ("UPLIFT_AFTER_FX", "COST_AT_TT_SELL")

    def test_quotes_under_the_new_version_use_the_bsp_sides(self, policies):
        e = engine(date(2026, 10, 14))
        assert e._convert_fcy_to_pgk(D("100"), "AUD") == D("327.41")       # 100 / (0.3215 x 0.95)
        assert e._convert_pgk_to_fcy(D("1000"), "AUD") == D("337.15")      # 1000 x 0.3065 = 306.50 x 1.10
        assert [c["legs"][0]["side"] for c in e._conversions] == ["TT_BUY", "TT_SELL"]

    def test_quotes_dated_under_the_superseded_version_fail_closed_on_conversion(self, policies):
        e = engine(date(2026, 10, 12))
        with pytest.raises(SupersededFxConventionError):
            e._convert_fcy_to_pgk(D("100"), "AUD")
        with pytest.raises(SupersededFxConventionError):
            e._convert_pgk_to_fcy(D("1000"), "AUD")

    def test_no_conversion_needs_no_fx_and_no_caf_under_either_version(self, policies):
        FxMarketRate.objects.all().delete()
        for day in (date(2026, 10, 12), date(2026, 10, 14)):
            e = engine(day)
            assert e._convert_cross_currency(D("100"), "PGK", "PGK") == D("100")
            assert e._conversions == []
