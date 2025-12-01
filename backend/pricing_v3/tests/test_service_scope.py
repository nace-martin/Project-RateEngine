from django.test import TestCase
from core.models import Location, Country, City, Policy, FxSnapshot
from pricing_v3.models import RateCard, RateLine, Zone, ZoneMember, ChargeMethod
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from quotes.models import Quote, QuoteVersion
from parties.models import Company
from pricing_v3.resolvers import QuoteContextBuilder, BuyChargeResolver
from datetime import date
from django.utils import timezone

class ServiceScopeTestCase(TestCase):
    def setUp(self):
        # Setup Policy
        self.policy = Policy.objects.create(
            name="Default Policy",
            effective_from=timezone.now()
        )
        
        # Setup FxSnapshot
        self.fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="Test Source",
            rates={"AUD": 1.0, "PGK": 2.5, "USD": 0.65},
            caf_percent=0.05,
            fx_buffer_percent=0.02
        )

        # Setup Geography
        self.country = Country.objects.create(code="AU", name="Australia")
        self.city = City.objects.create(country=self.country, name="Brisbane")
        self.loc_origin = Location.objects.create(code="BNE", name="Brisbane", kind="AIRPORT", city=self.city, country=self.country)
        self.loc_dest = Location.objects.create(code="POM", name="Port Moresby", kind="AIRPORT")
        
        self.zone_origin = Zone.objects.create(code="Z-BNE", name="Brisbane Zone", mode="AIR")
        ZoneMember.objects.create(zone=self.zone_origin, location=self.loc_origin)
        
        self.zone_dest = Zone.objects.create(code="Z-POM", name="POM Zone", mode="AIR")
        ZoneMember.objects.create(zone=self.zone_dest, location=self.loc_dest)

        # Setup Components
        self.comp_pickup = ServiceComponent.objects.create(code="PICKUP", description="Pickup", mode="AIR", leg="ORIGIN")
        self.comp_freight = ServiceComponent.objects.create(code="FREIGHT", description="Air Freight", mode="AIR", leg="MAIN")

        # Setup Supplier & Rate Card
        self.supplier = Company.objects.create(name="Test Supplier", company_type="SUPPLIER")
        self.customer = Company.objects.create(name="Test Customer", company_type="CUSTOMER")
        
        self.rate_card = RateCard.objects.create(
            supplier=self.supplier,
            mode="AIR",
            origin_zone=self.zone_origin,
            destination_zone=self.zone_dest,
            currency="AUD",
            scope="CONTRACT",
            name="Test Rates"
        )
        # Add rates for BOTH Pickup and Freight
        RateLine.objects.create(card=self.rate_card, component=self.comp_pickup, method="FLAT", min_charge=50)
        RateLine.objects.create(card=self.rate_card, component=self.comp_freight, method="FLAT", min_charge=100)

        # Setup Service Rule for A2A (Airport to Airport) - EXCLUDES Pickup
        self.rule_a2a = ServiceRule.objects.create(
            mode="AIR",
            direction="EXPORT",
            incoterm="FOB",
            payment_term="PREPAID",
            service_scope="A2A",
            description="Air Export A2A FOB"
        )
        # Only add Freight to the rule
        ServiceRuleComponent.objects.create(service_rule=self.rule_a2a, service_component=self.comp_freight)

    def test_scope_filtering(self):
        # Create Quote with A2A Scope
        quote = Quote.objects.create(
            quote_number="Q-1001",
            customer=self.customer,
            mode="AIR",
            shipment_type="EXPORT",
            incoterm="FOB",
            payment_term="PREPAID",
            service_scope="A2A",
            origin_location=self.loc_origin,
            destination_location=self.loc_dest,
            status="DRAFT",
            fx_snapshot=self.fx_snapshot
        )
        QuoteVersion.objects.create(quote=quote, version_number=1, status="DRAFT")

        # Simulate View Logic
        context = QuoteContextBuilder.build(quote.id)
        
        # This is the logic we fixed in views.py
        rule = ServiceRule.objects.filter(
            mode=context.quote.mode,
            direction=context.quote.shipment_type,
            incoterm=context.quote.incoterm,
            payment_term=context.quote.payment_term,
            service_scope=context.quote.service_scope,
            is_active=True
        ).order_by("-effective_from").first()

        self.assertIsNotNone(rule)
        self.assertEqual(rule, self.rule_a2a)

        components = list(rule.service_components.filter(is_active=True))
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].code, "FREIGHT")

        # Resolve Charges
        resolver = BuyChargeResolver(context)
        buy_charges = resolver.resolve_all(components)

        # Assertions
        charge_codes = [c.component_code for c in buy_charges]
        self.assertIn("FREIGHT", charge_codes)
        self.assertNotIn("PICKUP", charge_codes)
