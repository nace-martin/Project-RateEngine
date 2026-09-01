from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from pricing_v4.engine.domestic_engine import (
    DOMESTIC_TARIFF_CURRENCY,
    DomesticPricingEngine,
)
from pricing_v4.models import Carrier, DomesticCOGS, DomesticSellRate, ProductCode


class DomesticCurrencyBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.freight = ProductCode.objects.create(
            id=3981,
            code="DOM-FRT-AIR",
            description="Domestic Air Freight",
            domain=ProductCode.DOMAIN_DOMESTIC,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_KG,
        )
        cls.carrier = Carrier.objects.create(
            code="PX-CURRENCY-BOUNDARY",
            name="Air Niugini Currency Boundary",
            carrier_type="AIRLINE",
        )
        valid_from = date.today() - timedelta(days=30)
        valid_until = date.today() + timedelta(days=365)

        # Governed domestic tariff row that must be selected regardless of the
        # international/caller BUY currency carried into this engine.
        cls.pgk_cogs = DomesticCOGS.objects.create(
            product_code=cls.freight,
            origin_zone="POM",
            destination_zone="LAE",
            carrier=cls.carrier,
            currency="PGK",
            rate_per_kg=Decimal("6.10"),
            valid_from=valid_from,
            valid_until=valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=cls.freight,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg=Decimal("7.30"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

        # Deliberate decoy. Before the boundary hardening, incoming USD could
        # select this row instead of the governed PGK domestic tariff.
        DomesticCOGS.objects.create(
            product_code=cls.freight,
            origin_zone="POM",
            destination_zone="LAE",
            carrier=cls.carrier,
            currency="USD",
            rate_per_kg=Decimal("99.00"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def test_international_buy_currency_cannot_change_domestic_tariff_selection(self):
        for incoming_buy_currency in ("USD", "AUD"):
            with self.subTest(incoming_buy_currency=incoming_buy_currency):
                result = DomesticPricingEngine(
                    cogs_origin="POM",
                    destination="LAE",
                    weight_kg=Decimal("100"),
                    service_scope="A2A",
                    preferred_carrier_id=self.carrier.id,
                    buy_currency=incoming_buy_currency,
                ).calculate_quote()

                freight_line = next(
                    line for line in result.line_items
                    if line.product_code == "DOM-FRT-AIR"
                )

                self.assertEqual(DOMESTIC_TARIFF_CURRENCY, "PGK")
                self.assertEqual(result.quote_currency, "PGK")
                self.assertEqual(result.currency, "PGK")
                self.assertEqual(result.total_cost_pgk, Decimal("610.00"))
                self.assertEqual(result.total_sell_pgk, Decimal("730.00"))
                self.assertEqual(freight_line.cost_currency, "PGK")
                self.assertEqual(freight_line.sell_currency, "PGK")
                self.assertFalse(freight_line.is_rate_missing)
                self.assertEqual(
                    result.audit_metadata["selected_rates"][0]["rate"]["id"],
                    self.pgk_cogs.id,
                )
