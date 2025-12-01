import json
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from core.models import Location, FxSnapshot, Policy, Country, City, Airport
from quotes.models import Quote
from services.models import ServiceComponent
from parties.models import Company, CustomerCommercialProfile

from pricing_v3.engine_types import BuyCharge, ChargeMethod, ChargeUnit
from pricing_v3.resolvers import QuoteContextBuilder
from pricing_v3.charge_engine import ChargeEngine

class ChargeEngineTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Customer")
        self.location = Location.objects.create(kind="AIRPORT", name="BNE", code="BNE")
        
        self.policy = Policy.objects.create(
            name="Test Policy", 
            effective_from=timezone.now(),
            margin_pct=Decimal("0.10"), # 10% default
            caf_import_pct=Decimal("0.05")
        )
        
        self.fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(), 
            source="Test", 
            rates=json.dumps({"USD": {"tt_buy": 0.30, "tt_sell": 0.28}}),
            fx_buffer_percent=Decimal("0.02") # 2% buffer
        )
        
        self.quote = Quote.objects.create(
            customer=self.company,
            origin_location=self.location,
            destination_location=self.location,
            mode="AIR",
            policy=self.policy,
            fx_snapshot=self.fx_snapshot,
            output_currency="PGK"
        )
        
        self.context = QuoteContextBuilder.build(str(self.quote.id))
        self.context.chargeable_weight = Decimal("100.00")
        
        self.engine = ChargeEngine(self.context)

    def test_calculate_sell_charges_basic(self):
        # Buy: 100 USD flat
        buy = BuyCharge(
            source='SPOT', supplier_id=None, component_code='FRT',
            currency='USD', method='FLAT', unit=None,
            flat_amount=Decimal("100.00")
        )
        
        sell_charges = self.engine.calculate_sell_charges([buy])
        self.assertEqual(len(sell_charges), 1)
        sell = sell_charges[0]
        
        # 1. Cost PGK: 100 USD / 0.30 (tt_buy) = 333.33 PGK
        # Note: No buffer on buy side
        # 1. Cost PGK: 100 USD * 3.33 (tt_buy) = 333.00 PGK
        # We need to update the rates in setUp to be PGK per FCY
        # Let's say 1 USD = 3.33 PGK (Buy) and 1 USD = 3.57 PGK (Sell)
        # Note: Sell rate (PGK->USD) is usually lower in indirect terms (1 PGK = 0.28 USD)
        # But here we are storing direct rates (PGK per FCY).
        # So Sell Rate (Bank Sells USD) = 3.57 PGK per USD.
        
        # Updating setup in a new test method or overriding here would be cleaner, 
        # but let's just assume the rates in setUp are "PGK per FCY".
        # 0.30 PGK per USD is unrealistic (USD is stronger).
        # Let's update the rates in the test.
        
        self.fx_snapshot.rates = json.dumps({"USD": {"tt_buy": 3.33, "tt_sell": 3.57}})
        self.fx_snapshot.save()
        
        # Re-init engine to reload rates
        self.engine = ChargeEngine(self.context)
        
        sell_charges = self.engine.calculate_sell_charges([buy])
        sell = sell_charges[0]

        # Cost: 100 * 3.33 = 333.00 PGK
        self.assertEqual(sell.total_cost_pgk, Decimal("333.00"))
        
        # Margin: 10% -> 333 * 1.10 = 366.30 PGK
        self.assertEqual(sell.total_sell_pgk, Decimal("366.30"))
        
        # Sell FCY (PGK): Output currency is PGK, so it should match sell_pgk
        # Wait, output currency is PGK in setUp.
        self.assertEqual(sell.total_sell_fcy, Decimal("366.30"))
        
        # Let's test USD output
        self.context.quote.output_currency = "USD"
        self.context.quote.save()
        
        sell_charges = self.engine.calculate_sell_charges([buy])
        sell = sell_charges[0]
        
        # Sell PGK is still 366.30
        # Sell USD: 366.30 / 3.57 (Sell Rate) ... wait, logic check.
        # Logic: `fx_rate_sell = self._get_exchange_rate("PGK", sell_currency, use_buffer=True)`
        # `_get_exchange_rate` for PGK->USD:
        # `base_rate = info["tt_sell"]` (3.57)
        # `rate = 1.0 / base_rate` (1/3.57 = 0.2801...)
        # `rate *= (1 + buffer)` (0.2801 * 1.02 = 0.2857...)
        # `sell_fcy = sell_pgk * rate` (366.30 * 0.2857...)
        
        # Let's verify the math.
        # 366.30 PGK to USD.
        # Bank Sells USD at 3.57 PGK/USD.
        # So 366.30 / 3.57 = 102.60 USD.
        # Buffer 2% on the RATE?
        # If we buffer the rate (make it higher/lower?), we want to be safe.
        # If we are converting to USD to quote the customer, we want to make sure 
        # that when they pay us 102.60 USD, we get at least 366.30 PGK.
        # If rate moves to 3.60, 102.60 USD = 369 PGK (Good).
        # If rate moves to 3.50, 102.60 USD = 359 PGK (Bad, loss).
        # So we want to divide by a HIGHER rate (weaker PGK) to be safe?
        # Or multiply by a LOWER factor?
        # My logic: `rate *= (1 + buffer)`.
        # rate is 1/3.57 = 0.28.
        # rate * 1.02 = 0.285.
        # 366.30 * 0.285 = 104.39 USD.
        # If we quote 104.39 USD, and customer pays, we convert back at 3.57 (spot).
        # 104.39 * 3.57 = 372.67 PGK.
        # This is > 366.30. So we are safe. Buffer adds to the sell price.
        
        base_rate = Decimal("1.0") / Decimal("3.57")
        buffered_rate = base_rate * Decimal("1.02")
        expected_usd = (Decimal("366.30") * buffered_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        self.assertEqual(sell.total_sell_fcy, expected_usd)

    def test_margin_override(self):
        # Create profile with override
        CustomerCommercialProfile.objects.create(
            company=self.company,
            default_margin_percent=Decimal("20.00")
        )
        # Re-build context to pick up profile
        context = QuoteContextBuilder.build(str(self.quote.id))
        engine = ChargeEngine(context)
        
        buy = BuyCharge(
            source='SPOT', supplier_id=None, component_code='FRT',
            currency='PGK', method='FLAT', flat_amount=Decimal("100.00")
        )
        
        sell = engine.calculate_sell_charges([buy])[0]
        
        # Margin should be 20% (0.20), not policy 10%
        self.assertEqual(sell.margin_percent, Decimal("0.20"))
        self.assertEqual(sell.total_sell_pgk, Decimal("120.00"))

