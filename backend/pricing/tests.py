from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from .dataclasses import ShipmentInput, Piece
from .services.pricing_service import compute_quote
from core.models import Stations, Providers, CurrencyRates
from organizations.models import Organizations
from pricing.models import Audience, Routes, Ratecards, Lanes, LaneBreaks, PricingPolicy

class PricingServiceGatewayRoutingTests(TestCase):
    def setUp(self):
        """Set up necessary data for testing the pricing service."""
        # Create Audiences
        self.png_customer, _ = Audience.objects.get_or_create(
            party_type="CUSTOMER", region="PNG", settlement="PREPAID",
            defaults={'code': "PNG_CUSTOMER_PREPAID", 'is_active': True}
        )
        self.agent_collect, _ = Audience.objects.get_or_create(
            party_type="AGENT", region="OVERSEAS", settlement="COLLECT",
            defaults={'code': "OVERSEAS_AGENT_COLLECT", 'is_active': True}
        )

        # Create Organization
        self.organization = Organizations.objects.create(
            name="Test Org",
            audience=self.png_customer.code,
            gst_pct=Decimal('10.00'),
            default_sell_currency='PGK'
        )

        # Create Stations
        self.bne = Stations.objects.create(iata="BNE", city="Brisbane", country="AU", max_service_level="DOOR_DOOR")
        self.syd = Stations.objects.create(iata="SYD", city="Sydney", country="AU", max_service_level="DOOR_DOOR")
        self.pom = Stations.objects.create(iata="POM", city="Port Moresby", country="PG", max_service_level="DOOR_DOOR")
        self.lae = Stations.objects.create(iata="LAE", city="Lae", country="PG", max_service_level="DOOR_DOOR")
        self.hgu = Stations.objects.create(iata="HGU", city="Mount Hagen", country="PG", max_service_level="AIRPORT_ONLY")

        # Create Routes
        self.au_pg_import = Routes.objects.create(
            name="AU to PG Import", origin_country="AU", dest_country="PG", shipment_type="IMPORT"
        )
        self.pg_au_export = Routes.objects.create(
            name="PG to AU Export", origin_country="PG", dest_country="AU", shipment_type="EXPORT"
        )
        self.pg_domestic = Routes.objects.create(
            name="PG Domestic", origin_country="PG", dest_country="PG", shipment_type="DOMESTIC"
        )

        # Create a minimal set of rate cards and lanes to allow pricing to complete
        self.setup_dummy_rates()

    def setup_dummy_rates(self):
        """Creates minimal rate data to satisfy the pricing engine."""
        now = timezone.now()
        provider, _ = Providers.objects.get_or_create(name="Dummy Air", defaults={'provider_type': "AIRLINE"})

        # Create dummy FX rates
        CurrencyRates.objects.create(
            as_of_ts=now, base_ccy="USD", quote_ccy="PGK", rate=Decimal("3.50"), rate_type="BUY"
        )
        CurrencyRates.objects.create(
            as_of_ts=now, base_ccy="PGK", quote_ccy="USD", rate=Decimal("0.28"), rate_type="SELL"
        )
        CurrencyRates.objects.create(
            as_of_ts=now, base_ccy="PGK", quote_ccy="AUD", rate=Decimal("0.45"), rate_type="SELL"
        )
        CurrencyRates.objects.create(
            as_of_ts=now, base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.20"), rate_type="BUY"
        )


        # Create Pricing Policies
        PricingPolicy.objects.get_or_create(audience="PNG_CUSTOMER_PREPAID", defaults={'gst_applies': True, 'gst_pct': 10.0})
        PricingPolicy.objects.get_or_create(audience="OVERSEAS_AGENT_COLLECT", defaults={'gst_applies': False, 'gst_pct': 0.0})

        # Create dummy rate cards (BUY and SELL)
        buy_card_intl = Ratecards.objects.create(
            provider=provider, name="BuyIntl", role="BUY", scope="INTERNATIONAL", direction="EXPORT",
            audience=self.agent_collect, currency="USD", source="TEST", status="ACTIVE",
            effective_date="2024-01-01", meta={}, created_at=now, updated_at=now
        )
        buy_card_dom = Ratecards.objects.create(
            provider=provider, name="BuyDom", role="BUY", scope="DOMESTIC", direction="DOMESTIC",
            audience=self.agent_collect, currency="PGK", source="TEST", status="ACTIVE",
            effective_date="2024-01-01", meta={}, created_at=now, updated_at=now
        )
        Ratecards.objects.create(
            provider=provider, name="SellIntlImport", role="SELL", scope="INTERNATIONAL", direction="IMPORT",
            audience=self.png_customer, currency="PGK", source="TEST", status="ACTIVE",
            effective_date="2024-01-01", meta={}, created_at=now, updated_at=now
        )
        Ratecards.objects.create(
            provider=provider, name="SellIntlExport", role="SELL", scope="INTERNATIONAL", direction="EXPORT",
            audience=self.png_customer, currency="PGK", source="TEST", status="ACTIVE",
            effective_date="2024-01-01", meta={}, created_at=now, updated_at=now
        )
        Ratecards.objects.create(
            provider=provider, name="SellDom", role="SELL", scope="DOMESTIC", direction="DOMESTIC",
            audience=self.png_customer, currency="PGK", source="TEST", status="ACTIVE",
            effective_date="2024-01-01", meta={}, created_at=now, updated_at=now
        )

        # Create lanes and breaks for all required legs
        lanes_to_create = [
            (buy_card_intl, self.bne, self.pom),
            (buy_card_dom, self.pom, self.lae),
            (buy_card_dom, self.lae, self.pom),
            (buy_card_intl, self.pom, self.syd),
            (buy_card_dom, self.pom, self.hgu),
            (buy_card_intl, self.bne, self.hgu),
        ]
        for card, origin, dest in lanes_to_create:
            lane = Lanes.objects.create(ratecard=card, origin=origin, dest=dest, is_direct=True)
            LaneBreaks.objects.create(lane=lane, break_code="MIN", min_charge=100.00)
            LaneBreaks.objects.create(lane=lane, break_code="N", per_kg=5.00)

    def test_import_to_outer_port_uses_gateway(self):
        """Test that an import from BNE to LAE is routed via POM."""
        shipment = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="LAE",
            payment_term="PREPAID",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=100, length_cm=50, width_cm=50, height_cm=50)]
        )
        result = compute_quote(shipment)

        snapshot = result.snapshot
        legs = snapshot.get("legs_breaks", [])
        self.assertEqual(len(legs), 2, "Should create two legs for gateway routing")

        leg_descs = [line.description for line in result.buy_lines if line.code == "FREIGHT"]
        self.assertIn("BNE->POM", leg_descs[0])
        self.assertIn("POM->LAE", leg_descs[1])

    def test_export_from_outer_port_uses_gateway(self):
        """Test that an export from LAE to SYD is routed via POM."""
        shipment = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="LAE",
            dest_iata="SYD",
            payment_term="PREPAID",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=100, length_cm=50, width_cm=50, height_cm=50)]
        )
        result = compute_quote(shipment)

        snapshot = result.snapshot
        legs = snapshot.get("legs_breaks", [])
        self.assertEqual(len(legs), 2, "Should create two legs for gateway routing")

        leg_descs = [line.description for line in result.buy_lines if line.code == "FREIGHT"]
        self.assertIn("LAE->POM", leg_descs[0])
        self.assertIn("POM->SYD", leg_descs[1])

    def test_door_to_door_to_outer_port_is_manual(self):
        """Test that a DTD request to HGU (an outer port) triggers a manual rate."""
        shipment = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="HGU", # HGU is 'AIRPORT_ONLY'
            payment_term="PREPAID",
            service_scope="DOOR_DOOR",
            pieces=[Piece(weight_kg=100, length_cm=50, width_cm=50, height_cm=50)]
        )
        result = compute_quote(shipment)
        snapshot = result.snapshot
        self.assertTrue(snapshot.get("manual_rate_required"))
        self.assertIn(
            "Door-to-Door service is not available for the route BNE to HGU.",
            snapshot.get("manual_reasons", [])
        )

    def test_standard_domestic_quote(self):
        """Test a standard domestic quote from POM to LAE has one leg."""
        shipment = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="POM",
            dest_iata="LAE",
            payment_term="PREPAID",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=100, length_cm=50, width_cm=50, height_cm=50)]
        )
        result = compute_quote(shipment)
        snapshot = result.snapshot
        legs = snapshot.get("legs_breaks", [])
        self.assertEqual(len(legs), 1)
        leg_descs = [line.description for line in result.buy_lines if line.code == "FREIGHT"]
        self.assertIn("POM->LAE", leg_descs[0])

    def test_standard_import_to_gateway(self):
        """Test a standard import from BNE to POM has one leg."""
        shipment = ShipmentInput(
            org_id=self.organization.id,
            origin_iata="BNE",
            dest_iata="POM",
            payment_term="PREPAID",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=100, length_cm=50, width_cm=50, height_cm=50)]
        )
        result = compute_quote(shipment)
        snapshot = result.snapshot
        legs = snapshot.get("legs_breaks", [])
        self.assertEqual(len(legs), 1)
        leg_descs = [line.description for line in result.buy_lines if line.code == "FREIGHT"]
        self.assertIn("BNE->POM", leg_descs[0])
