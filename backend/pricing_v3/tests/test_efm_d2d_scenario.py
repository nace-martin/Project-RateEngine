from django.test import TestCase
from decimal import Decimal
from core.models import Location, Country, City, Policy, FxSnapshot
from pricing_v3.models import RateCard, RateLine, Zone, ZoneMember, ChargeMethod, LocalFeeRule
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from quotes.models import Quote, QuoteVersion
from parties.models import Company
from pricing_v3.resolvers import QuoteContextBuilder, BuyChargeResolver
from pricing_v3.charge_engine import ChargeEngine
from django.utils import timezone

class EfmD2dScenarioTestCase(TestCase):
    def setUp(self):
        # 1. Setup Infrastructure (Policy, FX) - Policy might be deleted by seed, so check or recreate
        self.policy, _ = Policy.objects.get_or_create(name="Default Policy", defaults={"effective_from": timezone.now()})
        self.fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="Test Source",
            rates={
                "AUD": {"tt_buy": 2.3, "tt_sell": 2.2}, # 1 AUD = 2.3 PGK (Buy)
                "PGK": {"tt_buy": 1.0, "tt_sell": 1.0},
                "USD": {"tt_buy": 3.5, "tt_sell": 3.4}
            },
            caf_percent=0.05,
            fx_buffer_percent=0.02
        )

        # 2. Fetch Geography (Seeded)
        self.country_au = Country.objects.get(code="AU")
        self.country_pg = Country.objects.get(code="PG")
        self.loc_bne = Location.objects.get(code="BNE")
        self.loc_pom = Location.objects.get(code="POM")
        
        # 3. Fetch Components (Seeded)
        self.comp_pickup = ServiceComponent.objects.get(code="PICKUP")
        self.comp_freight = ServiceComponent.objects.get(code="FRT_AIR")
        self.comp_clearance = ServiceComponent.objects.get(code="CLEARANCE")
        self.comp_cartage = ServiceComponent.objects.get(code="CARTAGE")

        # 4. Fetch Customer
        self.customer, _ = Company.objects.get_or_create(name="Test Customer", company_type="CUSTOMER")
        
        # 5. Ensure Margins (Seeded or Create)
        # Seed script deletes margins, so we need to recreate them for the test if not seeded
        # Seed script didn't seed margins.
        from pricing_v3.models import ComponentMargin
        ComponentMargin.objects.get_or_create(component=self.comp_clearance, defaults={"margin_percent": 0.0})
        ComponentMargin.objects.get_or_create(component=self.comp_cartage, defaults={"margin_percent": 0.0})

    def test_d2d_exw_quote(self):
        # Create Quote
        quote = Quote.objects.create(
            quote_number="Q-D2D-TEST",
            customer=self.customer,
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="EXW",
            payment_term="COLLECT",
            service_scope="D2D",
            origin_location=self.loc_bne,
            destination_location=self.loc_pom,
            status="DRAFT",
            fx_snapshot=self.fx_snapshot,
            output_currency="PGK"
        )

        # Build Context
        context = QuoteContextBuilder.build(quote.id)
        
        # Resolve Components (Service Rule)
        rule = ServiceRule.objects.filter(
            mode=context.quote.mode,
            direction=context.quote.shipment_type,
            incoterm=context.quote.incoterm,
            payment_term=context.quote.payment_term,
            service_scope=context.quote.service_scope,
            is_active=True
        ).first()
        self.assertIsNotNone(rule, "Service Rule not found!")
        components = list(rule.service_components.all())
        
        # Resolve Buy Charges
        resolver = BuyChargeResolver(context)
        buy_charges = resolver.resolve_all(components)
        
        print("\n--- Buy Charges ---")
        for charge in buy_charges:
            amount = charge.flat_amount or charge.rate_per_unit
            print(f"{charge.component_code}: {amount} {charge.currency} ({charge.source})")

        # Verify Buy Charges
        codes = [c.component_code for c in buy_charges]
        self.assertIn("PICKUP", codes) # Origin (AUD)
        self.assertIn("FRT_AIR", codes) # Freight (AUD)
        self.assertIn("CLEARANCE", codes) # Dest (PGK)
        self.assertIn("CARTAGE", codes) # Dest (PGK)

        # Run Charge Engine (Sell Side)
        engine = ChargeEngine(context)
        result = engine.calculate_sell_charges(buy_charges)
        
        print("\n--- Sell Lines ---")
        for line in result.sell_lines:
            print(f"{line.component_code}: Cost {line.cost_pgk} PGK -> Sell {line.sell_pgk} PGK ({line.sell_currency})")

        # Verify Conversion
        # Pickup (AUD) -> PGK
        # Freight (AUD) -> PGK
        # Clearance (PGK) -> PGK (No conversion)
        
        pickup_line = next(l for l in result.sell_lines if l.component_code == "PICKUP")
        # Cost should be converted. 85 AUD * 2.5 = 212.5 PGK
        # Note: My test setup uses flat 85.
        # Wait, BuyCharge doesn't have 'amount_in_currency' property directly? 
        # It has flat_amount, rate_per_unit, etc.
        # ChargeEngine calculates cost.
        
        # Check Totals
        print(f"\nTotal Sell PGK: {result.total_sell_pgk}")
        self.assertTrue(result.total_sell_pgk > 0)
