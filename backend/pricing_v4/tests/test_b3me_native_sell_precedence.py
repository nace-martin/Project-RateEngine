"""Pilot Gate B3M-E: a native SELL tariff in the quote currency takes priority over any conversion.

Import destination charges are priced from the Rate Matrix in the stage-2 shadow engine (the only import
Rate Matrix path). Export native-SELL precedence is tested in test_b3me_export_production.py. Synthetic data only.
"""

from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from core.fx_market_models import FxMarketRate
from core.models import Currency
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.rate_matrix_models import RateLine
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm as ImportTerm, ServiceScope
from pricing_v4.services.rate_matrix_stage2_shadow import MatrixShadowImportEngine, Scenario, _MatrixLookup
from pricing_v4.tests.test_rate_matrix_stage2_shadow import (  # noqa: F401  (world is a fixture)
    DOC,
    LANE,
    TERM,
    TODAY,
    _line,
    _sheet,
    world,
)

APPROVED = dict(
    margin_percent=D("16.67"), margin_method="TARGET_GROSS_MARGIN", export_caf_percent=D("10.00"),
    caf_method="TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
    fx_side_convention="FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL", fx_max_age_days=5,
    fx_primary_source="SYNTHETIC", fx_fallback_source="MANUAL",
)


@pytest.fixture
def approved(world):  # noqa: F811
    CommercialTermsPolicy.objects.update(**APPROVED)
    Currency.objects.get_or_create(code="USD", defaults={"name": "Synthetic USD"})
    usd = _sheet(world, "Synthetic SELL USD", "SELL", "USD")
    _line(world, usd, DOC, "FLAT", destination="XPM", unit_rate=D("55"))
    return world


def import_matrix(term="PREPAID", currency="AUD", scope="A2D"):
    policy = CommercialTermsPolicy.objects.get()
    scenario = Scenario("XAA-XPM", D(100), term, scope, currency)
    eng = MatrixShadowImportEngine(
        matrix=_MatrixLookup(scenario, *LANE, TODAY, "default"),
        quote_date=TODAY, origin=LANE[0], destination=LANE[1], chargeable_weight_kg=D(100),
        payment_term=ImportTerm(term), service_scope=ServiceScope(scope), quote_currency=currency,
        caf_rate=policy.import_caf_rate, margin_rate=policy.margin_rate, margin_method=policy.margin_method,
        caf_method=policy.caf_method, fx_side_convention=policy.fx_side_convention,
        export_caf_rate=policy.export_caf_rate,
    )
    result = eng.calculate_quote()
    return {item.product_code: item for item in result.line_items}, result


def assert_native(line, amount, currency):
    assert (line.sell_amount, line.sell_currency) == (D(amount), currency)
    assert line.fx_applied is False and line.caf_applied is False and line.margin_applied is False
    assert not line.is_rate_missing


@pytest.mark.django_db
class TestImportDestinationNativeSell:
    @pytest.mark.parametrize("term, currency, amount", [
        ("COLLECT", "PGK", "165.00"), ("PREPAID", "AUD", "80.00"), ("PREPAID", "USD", "55.00"),
    ])
    def test_native_sell_in_the_quote_currency_is_used_without_fx_or_caf(self, approved, term, currency, amount):
        FxMarketRate.objects.all().delete()  # proves no FX is needed
        by, result = import_matrix(term=term, currency=currency)
        assert_native(by[DOC], amount, currency)
        assert result.audit_metadata["conversions"] == []

    def test_a_missing_native_fcy_sell_does_not_convert_the_pgk_tariff(self, approved):
        # A PGK DOC tariff exists; with no native USD TERM tariff the line is a visible gap, not PGK converted.
        assert RateLine.objects.filter(product_code__code=TERM, sheet__currency_code="PGK").exists()
        by, result = import_matrix(currency="USD")
        term = by.get(TERM)
        assert term is None or (term.is_rate_missing and term.sell_amount == D("0") and not term.fx_applied)
        assert result.audit_metadata["conversions"] == []  # nothing converted, so no FX and no CAF

    def test_explicit_native_sell_receives_no_margin(self, approved):
        before = import_matrix(currency="AUD")[0][DOC].sell_amount
        CommercialTermsPolicy.objects.update(margin_percent=D("40.00"), margin_method="MARKUP_ON_COST")
        assert import_matrix(currency="AUD")[0][DOC].sell_amount == before == D("80.00")

    def test_the_rate_matrix_path_has_no_legacy_pgk_default(self, approved):
        policy = CommercialTermsPolicy.objects.get()
        brokerage = SimpleNamespace(id=2020, code="IMP-CUS-CLR-DEST", description="Customs", category="CLEARANCE")
        common = dict(
            quote_date=TODAY, origin=LANE[0], destination=LANE[1], chargeable_weight_kg=D(100),
            payment_term=ImportTerm.COLLECT, service_scope=ServiceScope.A2D, quote_currency="PGK",
            caf_rate=policy.import_caf_rate, margin_rate=policy.margin_rate, margin_method=policy.margin_method,
        )
        legacy = ImportPricingEngine(**common)._missing_rate_line(brokerage, "DESTINATION")
        assert legacy.sell_amount == D("300.00")  # legacy behaviour, unchanged
        scenario = Scenario("XAA-XPM", D(100), "COLLECT", "A2D", "PGK")
        matrix = MatrixShadowImportEngine(matrix=_MatrixLookup(scenario, *LANE, TODAY, "default"), **common)
        line = matrix._missing_rate_line(brokerage, "DESTINATION")
        assert line.is_rate_missing and line.sell_amount == D("0") and not line.fx_applied

    def test_legacy_engine_keeps_its_pgk_fallback_for_comparison(self, approved):
        # Legacy production (LocalSellRate, PREPAID allow_pgk_fallback) is unchanged: with no USD row it
        # converts the PGK row. The Rate Matrix path above does not.
        policy = CommercialTermsPolicy.objects.get()
        legacy = ImportPricingEngine(
            quote_date=TODAY, origin=LANE[0], destination=LANE[1], chargeable_weight_kg=D(100),
            payment_term=ImportTerm.PREPAID, service_scope=ServiceScope.A2D, quote_currency="AUD",
            caf_rate=policy.import_caf_rate, margin_rate=policy.margin_rate, margin_method=policy.margin_method,
            caf_method=policy.caf_method, fx_side_convention=policy.fx_side_convention,
        ).calculate_quote()
        doc = {i.product_code: i for i in legacy.line_items}[DOC]
        assert (doc.sell_amount, doc.sell_currency, doc.fx_applied) == (D("80.00"), "AUD", False)
