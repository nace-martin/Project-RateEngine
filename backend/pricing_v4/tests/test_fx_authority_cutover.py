from datetime import date
from decimal import Decimal

import pytest

from core.fx_market_models import FxMarketRate
from core.fx_resolution import MissingFxRateError
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm as ExportPaymentTerm
from pricing_v4.engine.import_engine import (
    ImportPricingEngine,
    PaymentTerm as ImportPaymentTerm,
    ServiceScope,
)


QUOTE_DATE = date(2026, 9, 24)
MARKUP = "MARKUP_ON_COST"


def create_market_rate(
    base: str = "AUD",
    buy: str = "2.45000000",
    sell: str = "2.52000000",
    *,
    source: str = "BSP",
) -> FxMarketRate:
    buy_d = Decimal(buy)
    sell_d = Decimal(sell)
    return FxMarketRate.objects.create(
        base_currency=base,
        quote_currency="PGK",
        effective_date=QUOTE_DATE,
        tt_buy_rate=buy_d,
        tt_sell_rate=sell_d,
        mid_rate=(buy_d + sell_d) / Decimal(2),
        source=source,
    )


@pytest.mark.django_db
class TestPricingEngineFxAuthority:
    def test_export_collect_resolves_authoritative_fcy_pgk_market_rate(self):
        create_market_rate()

        engine = ExportPricingEngine(
            quote_date=QUOTE_DATE,
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("100"),
            payment_term=ExportPaymentTerm.COLLECT,
            destination_currency="AUD",
            caf_rate=Decimal("0.10"),
            margin_rate=Decimal("0.20"),
            margin_method=MARKUP,
        )

        assert engine.tt_buy == Decimal("2.45000000")
        assert engine.tt_sell == Decimal("2.52000000")
        # PGK -> AUD uses canonical PGK-per-AUD TT SELL plus Export CAF.
        assert engine._convert_pgk_to_fcy(Decimal("277.20")) == Decimal("100.00")

    def test_export_collect_missing_market_fx_fails_closed(self):
        with pytest.raises(MissingFxRateError):
            ExportPricingEngine(
                quote_date=QUOTE_DATE,
                origin="POM",
                destination="BNE",
                chargeable_weight_kg=Decimal("100"),
                payment_term=ExportPaymentTerm.COLLECT,
                destination_currency="AUD",
                caf_rate=Decimal("0.10"),
                margin_rate=Decimal("0.20"),
                margin_method=MARKUP,
            )

    def test_export_prepaid_pgk_does_not_require_fx(self):
        engine = ExportPricingEngine(
            quote_date=QUOTE_DATE,
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("100"),
            payment_term=ExportPaymentTerm.PREPAID,
            caf_rate=Decimal("0.10"),
            margin_rate=Decimal("0.20"),
            margin_method=MARKUP,
        )

        assert engine.quote_currency == "PGK"
        assert engine.tt_buy is None
        assert engine.tt_sell is None
        assert engine._convert_amount_to_pgk(Decimal("100"), "PGK") == Decimal("100.00")

    def test_import_prepaid_fcy_resolves_authoritative_market_rate(self):
        create_market_rate()

        engine = ImportPricingEngine(
            quote_date=QUOTE_DATE,
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100"),
            payment_term=ImportPaymentTerm.PREPAID,
            service_scope=ServiceScope.A2D,
            quote_currency="AUD",
            caf_rate=Decimal("0.05"),
            margin_rate=Decimal("0.20"),
            margin_method=MARKUP,
        )

        assert engine.tt_buy == Decimal("2.45000000")
        assert engine.tt_sell == Decimal("2.52000000")
        # Import PGK -> AUD divides by canonical TT SELL after 5% CAF deduction.
        assert engine._convert_pgk_to_fcy(Decimal("239.40"), "AUD") == Decimal("100.00")

    def test_import_prepaid_missing_market_fx_fails_closed(self):
        with pytest.raises(MissingFxRateError):
            ImportPricingEngine(
                quote_date=QUOTE_DATE,
                origin="BNE",
                destination="POM",
                chargeable_weight_kg=Decimal("100"),
                payment_term=ImportPaymentTerm.PREPAID,
                service_scope=ServiceScope.A2D,
                quote_currency="AUD",
                caf_rate=Decimal("0.05"),
                margin_rate=Decimal("0.20"),
                margin_method=MARKUP,
            )

    def test_import_collect_pgk_only_constructor_does_not_require_fx(self):
        engine = ImportPricingEngine(
            quote_date=QUOTE_DATE,
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100"),
            payment_term=ImportPaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D,
            quote_currency="PGK",
            caf_rate=Decimal("0.05"),
            margin_rate=Decimal("0.20"),
            margin_method=MARKUP,
        )

        assert engine.quote_currency == "PGK"
        assert engine.tt_buy is None
        assert engine.tt_sell is None
        assert engine._convert_cross_currency(Decimal("100"), "PGK", "PGK") == Decimal("100")

    def test_import_collect_foreign_cost_resolves_tt_buy_when_conversion_occurs(self):
        create_market_rate()
        engine = ImportPricingEngine(
            quote_date=QUOTE_DATE,
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100"),
            payment_term=ImportPaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
            quote_currency="PGK",
            caf_rate=Decimal("0.05"),
            margin_rate=Decimal("0.20"),
            margin_method=MARKUP,
        )

        # 100 AUD * (2.45 TT BUY * 95%) = 232.75 PGK.
        assert engine._convert_fcy_to_pgk(Decimal("100"), "AUD") == Decimal("232.75")
