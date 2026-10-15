"""Pilot Gate B3L-B: approved calculation conventions in the import engine.

Synthetic data only. Nothing here is an approved commercial value.
"""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from django.test import TestCase

from core.fx_market_models import FxMarketRate
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.models import Agent, ImportCOGS, LocalCOGSRate, LocalSellRate, ProductCode
from pricing_v4.services.commercial_policy import MissingCommercialPolicyError
from pricing_v4.services.fx_resolver import MissingFxMarketRateError

TODAY = date.today()
APPROVED = {
    "caf_method": "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
    "fx_side_convention": "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL",
}
SUPERSEDED = {"caf_method": "UPLIFT_AFTER_FX", "fx_side_convention": "COST_AT_TT_SELL"}


def engine(**kwargs):
    defaults = {
        "quote_date": TODAY, "origin": "SYD", "destination": "POM", "chargeable_weight_kg": D("100"),
        "payment_term": PaymentTerm.COLLECT, "service_scope": ServiceScope.D2D, "caf_rate": D("0.05"),
        "margin_rate": D("0.1667"), "margin_method": "TARGET_GROSS_MARGIN", **APPROVED,
    }
    defaults.update(kwargs)
    return ImportPricingEngine(**defaults)


class ApprovedConventionFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        CommercialTermsPolicy.objects.all().delete()
        CommercialTermsPolicy.objects.create(
            policy_code="SYNTH", valid_from=date(2020, 1, 1), margin_percent=D("16.67"),
            margin_method="TARGET_GROSS_MARGIN", import_caf_percent=D("5.00"), export_caf_percent=D("10.00"),
            gst_standard_percent=D("10.00"), **APPROVED,
            fx_max_age_days=5, fx_primary_source="TEST", fx_fallback_source="MANUAL", is_active=True,
        )
        FxMarketRate.objects.all().delete()
        FxMarketRate.objects.create(
            base_currency="AUD", quote_currency="PGK", effective_date=TODAY, tt_buy_rate=D("2.50"),
            tt_sell_rate=D("2.60"), mid_rate=D("2.55"), source="TEST",
        )


class TestConversionConventions(ApprovedConventionFixture):
    def test_fcy_cost_to_pgk_uses_tt_buy_with_the_caf_reducing_the_rate(self):
        e = engine()
        # BSP: FCY to PGK uses TT BUY; import CAF reduces the published rate: 100 x 2.50 / 0.95 = 263.16
        assert e._convert_fcy_to_pgk(D("100"), "AUD") == D("263.16")
        conversion = e._conversions[0]
        assert conversion["pure_market_amount"] == "250.00"
        assert conversion["caf_amount"] == "13.16"
        assert conversion["caf_operation"] == "PUBLISHED_RATE_REDUCED"
        assert conversion["legs"][0]["side"] == "TT_BUY" and D(str(conversion["legs"][0]["rate"])) == D("2.50")

    def test_import_caf_is_a_rate_reduction_not_an_uplift_on_the_amount(self):
        e = engine()
        pgk = e._convert_fcy_to_pgk(D("100"), "AUD")
        # / 0.95 is not x 1.05: 250.00 x 1.05 = 262.50, and the legacy rate adjustment gave 250 x 0.95 = 237.50
        assert pgk == D("263.16") and pgk not in (D("262.50"), D("237.50"))
        assert D(str(e._conversions[0]["legs"][0]["rate"])) == D("2.50")  # the market leg is recorded untouched
        assert D(e._conversions[0]["effective_rate_after_caf"]) == (D("2.50") / D("0.95")).quantize(D("0.00000001"))

    def test_pgk_to_customer_fcy_uses_tt_sell_then_export_caf_uplift(self):
        e = engine()
        # pure: 260.00 / 2.60 = 100.00 AUD ; export CAF uplift (policy 10%) 100.00 x 1.10 = 110.00
        assert e._convert_pgk_to_fcy(D("260.00"), "AUD") == D("110.00")
        conversion = e._conversions[0]
        assert conversion["legs"][0]["side"] == "TT_SELL" and D(str(conversion["legs"][0]["rate"])) == D("2.60")
        assert (conversion["pure_market_amount"], conversion["caf_operation"]) == ("100.00", "UPLIFTED_AFTER_FX")
        assert D(conversion["caf_percent"]) == D("10")

    def test_superseded_cost_at_tt_sell_policy_fails_closed_on_conversion(self):
        from pricing_v4.services.fx_conventions import SupersededFxConventionError

        with pytest.raises(SupersededFxConventionError):
            engine(**SUPERSEDED)._convert_fcy_to_pgk(D("100"), "AUD")
        with pytest.raises(SupersededFxConventionError):
            engine(**SUPERSEDED)._convert_pgk_to_fcy(D("100"), "AUD")

    def test_fcy_to_fcy_has_no_approved_rule_and_fails_closed(self):
        FxMarketRate.objects.create(
            base_currency="USD", quote_currency="PGK", effective_date=TODAY, tt_buy_rate=D("3.50"),
            tt_sell_rate=D("3.70"), mid_rate=D("3.60"), source="TEST",
        )
        with pytest.raises(MissingCommercialPolicyError, match="fails closed"):
            engine()._convert_cross_currency(D("100"), "AUD", "USD")
    def test_fcy_sell_amount_to_pgk_has_no_approved_side_and_fails_closed(self):
        with pytest.raises(MissingCommercialPolicyError, match="fails closed"):
            engine()._convert_cross_currency(D("100"), "AUD", "PGK", role="SELL")

    def test_no_conversion_means_no_caf_and_no_fx(self):
        FxMarketRate.objects.all().delete()
        e = engine()
        assert e._convert_cross_currency(D("100"), "AUD", "AUD") == D("100")
        assert e._convert_cross_currency(D("100"), "PGK", "PGK") == D("100")
        assert e._conversions == []

    def test_conversion_without_any_rate_fails_closed(self):
        FxMarketRate.objects.all().delete()
        with pytest.raises(MissingFxMarketRateError):
            engine()._convert_fcy_to_pgk(D("100"), "AUD")

    def test_zero_amounts_never_need_fx(self):
        FxMarketRate.objects.all().delete()
        assert engine()._convert_fcy_to_pgk(D("0"), "AUD") == D("0.00")

    def test_stale_rate_fails_closed_through_the_engine(self):
        FxMarketRate.objects.all().update(effective_date=TODAY - timedelta(days=6))
        from pricing_v4.services.fx_resolver import StaleFxMarketRateError

        with pytest.raises(StaleFxMarketRateError):
            engine()._convert_fcy_to_pgk(D("100"), "AUD")

    def test_rate_five_days_old_is_accepted(self):
        FxMarketRate.objects.all().update(effective_date=TODAY - timedelta(days=5))
        assert engine()._convert_fcy_to_pgk(D("100"), "AUD") == D("263.16")


class TestMarginConvention(ApprovedConventionFixture):
    def test_target_gross_margin_is_cost_over_one_minus_margin(self):
        # 273.00 / (1 - 0.1667) = 327.61
        sell = engine()._apply_margin(D("273.00"))
        assert sell == (D("273.00") / (D("1") - D("0.1667"))).quantize(D("0.01"))
        assert sell == D("327.61")
        margin = (sell - D("273.00")) / sell
        assert D("0.1666") < margin < D("0.1668")

    def test_it_is_not_the_legacy_20_percent_markup(self):
        legacy = engine(margin_rate=D("0.20"), margin_method="MARKUP_ON_COST")._apply_margin(D("273.00"))
        assert legacy == D("327.60")
        assert engine()._apply_margin(D("273.00")) != legacy

    def test_missing_margin_fails_closed(self):
        with pytest.raises(MissingCommercialPolicyError):
            engine(margin_rate=None)._apply_margin(D("1.00"))


class TestNoConversionQuote(ApprovedConventionFixture):
    """PREPAID AUD import: AUD costs and AUD destination sell, so no AUD/PGK FX is needed to price."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        FxMarketRate.objects.all().delete()  # the table is empty on purpose
        cls.pc_freight = ProductCode.objects.get_or_create(
            id=2901, defaults=dict(
                code="B3LB-FRT", description="Synthetic freight", domain="IMPORT", category="FREIGHT",
                is_gst_applicable=False, gst_rate=D("0"), gl_revenue_code="4100", gl_cost_code="5100",
                default_unit="KG", gst_treatment="ZERO_RATED"))[0]
        cls.pc_dest = ProductCode.objects.get_or_create(
            id=2902, defaults=dict(
                code="B3LB-DEST", description="Synthetic destination service", domain="IMPORT", category="CLEARANCE",
                is_gst_applicable=True, gst_rate=D("0.10"), gl_revenue_code="4200", gl_cost_code="5200",
                default_unit="SHIPMENT", gst_treatment="STANDARD"))[0]
        agent = Agent.objects.create(code="B3LB-AG", name="Synthetic Agent", country_code="AU", agent_type="ORIGIN")
        start, end = TODAY - timedelta(days=30), TODAY + timedelta(days=365)
        ImportCOGS.objects.create(
            product_code=cls.pc_freight, origin_airport="SYD", destination_airport="POM", agent=agent,
            currency="AUD", rate_per_kg=D("5.00"), valid_from=start, valid_until=end,
        )
        LocalCOGSRate.objects.create(
            product_code=cls.pc_dest, location="POM", direction="IMPORT", agent=agent, currency="AUD",
            rate_type="FIXED", amount=D("100.00"), valid_from=start, valid_until=end,
        )
        LocalSellRate.objects.create(
            product_code=cls.pc_dest, location="POM", direction="IMPORT", payment_term="PREPAID", currency="AUD",
            rate_type="FIXED", amount=D("150.00"), valid_from=start, valid_until=end,
        )

    def test_prices_with_an_empty_fx_table_and_records_no_conversion(self):
        e = engine(payment_term=PaymentTerm.PREPAID, quote_currency="AUD", buy_currency="AUD")
        result = e.calculate_quote()
        assert FxMarketRate.objects.count() == 0
        assert result.audit_metadata["conversions"] == []
        by_code = {line.product_code: line for line in result.line_items}
        dest = by_code["B3LB-DEST"]
        assert dest.sell_currency == "AUD" and dest.sell_amount == D("150.00")  # explicit tariff, not margined
        assert dest.caf_applied is False and dest.fx_applied is False
        assert dest.sell_pgk is None  # no conversion happened, so no PGK equivalent is invented
        assert dest.gst_rate == D("0.10") and dest.gst_amount == D("15.00")
        # A cost-plus line in the same currency is margined (cost / (1 - 0.1667)) with no CAF and no FX.
        origin = by_code["IMP-CUS-CLR-ORIGIN"]
        assert (origin.cost_amount, origin.sell_amount) == (D("500.00"), D("600.02"))
        assert origin.caf_applied is False and origin.fx_applied is False


class TestAdapterNeedsNoFxWithoutConversion(ApprovedConventionFixture):
    """The adapter must not pre-resolve FX: a PREPAID AUD import with AUD cost and AUD sell prices alone."""

    def test_prepaid_aud_import_prices_with_empty_fx_table(self):
        import uuid

        from core.dataclasses import LocationRef, Piece, QuoteInput, ShipmentDetails
        from pricing_v4.adapter import PricingServiceV4Adapter

        FxMarketRate.objects.all().delete()
        pc = ProductCode.objects.get_or_create(
            id=2903, defaults=dict(
                code="B3LB-ADP", description="Synthetic destination service", domain="IMPORT", category="CLEARANCE",
                is_gst_applicable=True, gst_rate=D("0.10"), gl_revenue_code="4200", gl_cost_code="5200",
                default_unit="SHIPMENT", gst_treatment="STANDARD"))[0]
        agent = Agent.objects.create(code="B3LB-AG2", name="Synthetic Agent 2", country_code="AU", agent_type="ORIGIN")
        start, end = date(2020, 1, 1), date(2099, 12, 31)
        LocalCOGSRate.objects.create(
            product_code=pc, location="POM", direction="IMPORT", agent=agent, currency="AUD", rate_type="FIXED",
            amount=D("100.00"), valid_from=start, valid_until=end,
        )
        LocalSellRate.objects.create(
            product_code=pc, location="POM", direction="IMPORT", payment_term="PREPAID", currency="AUD",
            rate_type="FIXED", amount=D("150.00"), valid_from=start, valid_until=end,
        )
        from services.models import ServiceComponent

        ServiceComponent.objects.get_or_create(
            code="B3LB-ADP",
            defaults={"description": "Synthetic destination service", "mode": "AIR", "leg": "DESTINATION",
                      "category": "CLEARANCE"},
        )
        bne = LocationRef(id=uuid.uuid4(), code="BNE", name="Brisbane", country_code="AU", currency_code="AUD")
        pom = LocationRef(id=uuid.uuid4(), code="POM", name="Port Moresby", country_code="PG", currency_code="PGK")
        shipment = ShipmentDetails(
            origin_location=bne, destination_location=pom, service_scope="A2D", payment_term="PREPAID",
            incoterm="DAP", shipment_type="IMPORT", mode="AIR", is_dangerous_goods=False, commodity_code="GCR",
            pieces=[Piece(pieces=1, length_cm=D(50), width_cm=D(50), height_cm=D(50), gross_weight_kg=D("100.0"))],
        )
        quote_input = QuoteInput(
            customer_id=uuid.uuid4(), contact_id=uuid.uuid4(), quote_date=TODAY, output_currency="AUD",
            shipment=shipment,
        )
        adapter = PricingServiceV4Adapter(quote_input)
        lines = adapter.calculate_charges()  # must not raise a missing-FX error
        assert FxMarketRate.objects.count() == 0
        assert lines.lines, "expected priced lines"
        audit = adapter._audit_metadata["fx_audit"]
        assert audit["applied"] is False and audit["conversions"] == []
        line = next(item for item in lines.lines if item.sell_fcy_currency == "AUD")
        assert line.sell_fcy == D("150.00")
        assert line.sell_pgk == D("0.00")  # unavailable, not invented
        assert audit["pgk_equivalent_complete"] is False
