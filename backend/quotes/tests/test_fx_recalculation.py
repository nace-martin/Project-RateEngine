from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import date
from rest_framework.test import APIClient

from core.models import Airport, City, Country, FxSnapshot, Currency, Policy, Location
from parties.models import Company, Contact
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent, LEG_CHOICES
from quotes.models import Quote, QuoteVersion

class QuoteFxRecalculationTests(TestCase):
    def setUp(self):
        # 1. Create user and authenticate
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tester_fx", email="t_fx@example.com", password="pass", is_staff=True, is_superuser=True, role='admin'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 2. Setup Currencies
        self.pgk, _ = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})
        self.aud, _ = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})

        # 3. Setup Locations (SYD -> POM)
        self.au_country, _ = Country.objects.get_or_create(code="AU", defaults={'name': 'Australia', 'currency': self.aud})
        self.pg_country, _ = Country.objects.get_or_create(code="PG", defaults={'name': 'Papua New Guinea', 'currency': self.pgk})
        
        self.syd_city, _ = City.objects.get_or_create(name="Sydney", country=self.au_country)
        self.pom_city, _ = City.objects.get_or_create(name="Port Moresby", country=self.pg_country)

        self.syd_airport, _ = Airport.objects.get_or_create(iata_code="SYD", defaults={'name': 'Sydney Airport', 'city': self.syd_city})
        self.pom_airport, _ = Airport.objects.get_or_create(iata_code="POM", defaults={'name': 'Jacksons International', 'city': self.pom_city})

        self.origin_loc, _ = Location.objects.get_or_create(
            airport=self.syd_airport,
            defaults={"name": "Sydney Location", "code": "SYD", "country": self.au_country, "city": self.syd_city, "is_active": True}
        )
        self.origin_loc.is_active = True
        self.origin_loc.save()

        self.destination_loc, _ = Location.objects.get_or_create(
            airport=self.pom_airport,
            defaults={"name": "POM Location", "code": "POM", "country": self.pg_country, "city": self.pom_city, "is_active": True}
        )
        self.destination_loc.is_active = True
        self.destination_loc.save()

        # 4. Setup Customer Company and Contact
        self.customer = Company.objects.create(name="FX Test Customer", is_customer=True)
        self.contact = Contact.objects.create(first_name="John", last_name="Doe", company=self.customer, email="john@example.com")

        # 5. Create Service Components and Rules for Import A2A
        # Note: We need a freight component and maybe origin/dest components
        self.freight, _ = ServiceComponent.objects.get_or_create(
            code='IMP-FRT-AIR', defaults={'description': 'Air Freight Cost', 'cost_type': 'COGS', 'unit': 'PER_KG', 'mode': 'AIR', 'leg': 'MAIN'}
        )
        self.agency, _ = ServiceComponent.objects.get_or_create(
            code='IMP-AGENCY-DEST', defaults={'description': 'Agency Destination', 'cost_type': 'SELL', 'unit': 'PER_SHIPMENT', 'mode': 'AIR', 'leg': 'DESTINATION'}
        )

        self.rule, _ = ServiceRule.objects.get_or_create(
            mode='AIR',
            direction='IMPORT',
            incoterm='DAP',
            payment_term='PREPAID',
            service_scope='A2A',
            defaults={'description': 'Import Rule A2A'},
        )
        ServiceRuleComponent.objects.get_or_create(service_rule=self.rule, service_component=self.freight, defaults={'sequence': 1})
        ServiceRuleComponent.objects.get_or_create(service_rule=self.rule, service_component=self.agency, defaults={'sequence': 2})

        # 6. Setup Policies to match remediated dev environment:
        # Launch Policy is active (20% margin, effective earlier)
        # Default Policy is inactive (5% margin, effective later)
        Policy.objects.get_or_create(
            name="Launch Policy",
            defaults={
                "margin_pct": Decimal("0.20"),
                "caf_import_pct": Decimal("0.05"),
                "caf_export_pct": Decimal("0.10"),
                "effective_from": timezone.now() - timezone.timedelta(days=100),
                "is_active": True,
            },
        )
        self.policy, _ = Policy.objects.get_or_create(
            name="Default Policy",
            defaults={
                "margin_pct": Decimal("0.05"),
                "caf_import_pct": Decimal("0.05"),
                "caf_export_pct": Decimal("0.05"),
                "effective_from": timezone.now() - timezone.timedelta(days=1),
                "is_active": False,
            },
        )

        # 7. Create baseline FxSnapshot with old AUD TT BUY = 0.35
        self.snap_old = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now() - timezone.timedelta(days=1),
            source="bsp_html",
            rates={"AUD": {"tt_buy": "0.3500", "tt_sell": "0.3500"}}
        )
        from django.urls import reverse
        print("REVERSED COMPUTE URL:", reverse("quotes:quote-compute-v3"))

    def test_draft_quote_recalculation_uses_latest_active_fx_rate(self):
        """
        Verify that a draft quote initially calculated with old FX rate (0.35)
        will update to the latest active rate (0.3315) when recalculated.
        """
        payload = {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": "A2A",
            "origin_location_id": str(self.origin_loc.id),
            "destination_location_id": str(self.destination_loc.id),
            "incoterm": "DAP",
            "payment_term": "PREPAID",
            "buy_currency": "AUD",
            "commodity_code": "GCR",
            "is_dangerous_goods": False,
            "dimensions": [
                {
                    "pieces": 1,
                    "length_cm": "100",
                    "width_cm": "100",
                    "height_cm": "100",
                    "gross_weight_kg": "100",
                    "package_type": "Box"
                }
            ],
            "overrides": []
        }

        # 1. First calculation (should use old rate 0.35)
        response = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        quote_id = response.json()["id"]
        
        # Verify FX Base Rate was 0.350000 and Effective FX was 0.3325 (0.35 * 0.95)
        quote_res = response.json()["quote_result"]
        self.assertAlmostEqual(Decimal(quote_res["fx_applied"]["base_rate"]), Decimal("0.35"))
        self.assertAlmostEqual(Decimal(quote_res["fx_applied"]["effective_fx_after_caf"]), Decimal("0.3325"))

        # 2. Create a new/latest FxSnapshot with AUD TT BUY = 0.3315
        self.snap_new = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="bsp_html",
            rates={"AUD": {"tt_buy": "0.3315", "tt_sell": "0.3315"}}
        )

        # 3. Recalculate using the same quote_id (should pull new rate 0.3315)
        payload["quote_id"] = quote_id
        response2 = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(response2.status_code, 201)

        # Verify FX Base Rate updated to 0.3315 and Effective FX updated to 0.3315 * 0.95 = 0.314925
        quote_res2 = response2.json()["quote_result"]
        self.assertAlmostEqual(Decimal(quote_res2["fx_applied"]["base_rate"]), Decimal("0.3315"))
        self.assertAlmostEqual(Decimal(quote_res2["fx_applied"]["effective_fx_after_caf"]), Decimal("0.314925"))

    def test_finalized_quotes_preserve_historical_snapshot(self):
        """
        Verify that finalized/accepted quotes do not silently change historical FX snapshots.
        """
        payload = {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": "A2A",
            "origin_location_id": str(self.origin_loc.id),
            "destination_location_id": str(self.destination_loc.id),
            "incoterm": "DAP",
            "payment_term": "PREPAID",
            "buy_currency": "AUD",
            "commodity_code": "GCR",
            "is_dangerous_goods": False,
            "dimensions": [
                {
                    "pieces": 1,
                    "length_cm": "100",
                    "width_cm": "100",
                    "height_cm": "100",
                    "gross_weight_kg": "100",
                    "package_type": "Box"
                }
            ],
            "overrides": []
        }

        # 1. Create quote
        response = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        quote_id = response.json()["id"]

        quote = Quote.objects.get(id=quote_id)
        # Lock quote by setting status to FINALIZED
        quote.status = Quote.Status.FINALIZED
        quote.save()

        # 2. Create new FxSnapshot
        self.snap_new = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="bsp_html",
            rates={"AUD": {"tt_buy": "0.3315", "tt_sell": "0.3315"}}
        )

        # 3. Attempting recalculation should fail since quote is locked
        payload["quote_id"] = quote_id
        response_recalc = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(response_recalc.status_code, 403)

        # 4. Request the quote details via GET and verify it still uses original 0.35 snapshot
        response_get = self.client.get(f"/api/v3/quotes/{quote_id}/")
        self.assertEqual(response_get.status_code, 200)
        quote_res = response_get.json()["quote_result"]
        self.assertAlmostEqual(Decimal(quote_res["fx_applied"]["base_rate"]), Decimal("0.35"))

    def test_usd_680_import_freight_recalculation(self):
        """
        Verify the exact USD 680 import freight calculation:
        - Buy: USD 680.00
        - Base FX: 0.235500
        - CAF import: 5%
        - Effective FX: 0.223725
        - Cost PGK: 3,039.45
        - Expected margin policy: 20% markup on cost (Launch Policy)
        - Expected Sell PGK: 3,647.34
        - Expected Margin PGK: 607.89
        - Expected Gross Margin % shown in UI terms: 16.67%
        """
        from quotes.models import SpotPricingEnvelopeDB, SPEChargeLineDB
        from pricing_v4.adapter import PricingServiceV4Adapter
        from core.dataclasses import QuoteInput, ShipmentDetails, Piece, LocationRef

        # Ensure USD currency exists
        usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})

        # Create FxSnapshot with USD rate = 0.2355
        FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="bsp_html",
            rates={"USD": {"tt_buy": "0.235500", "tt_sell": "0.235500"}}
        )

        # Create Spot Envelope
        spe = SpotPricingEnvelopeDB.objects.create(
            status="ready",
            created_by=self.user,
            expires_at=timezone.now() + timezone.timedelta(days=1),
            shipment_context_json={
                "origin_code": "SYD",
                "destination_code": "POM",
                "origin_country": "US",
                "destination_country": "PG",
                "total_weight_kg": 100,
                "pieces": 1,
            }
        )

        # Create Acknowledgement
        from quotes.models import SPEAcknowledgementDB
        SPEAcknowledgementDB.objects.create(
            envelope=spe,
            acknowledged_by=self.user,
            acknowledged_at=timezone.now(),
        )

        # Create Charge Line
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="IMP-FRT-AIR",
            description="Import Air Freight",
            amount=Decimal("6.80"),  # 6.80 * 100 = 680 USD
            currency="USD",
            unit="per_kg",
            bucket="airfreight",
            entered_at=timezone.now(),
            source_reference="manual",
            is_primary_cost=True,
        )

        # Build QuoteInput manually
        origin_ref = LocationRef(
            id=self.origin_loc.id, code=self.origin_loc.code, name=self.origin_loc.name,
            country_code="US", currency_code="USD",
        )
        dest_ref = LocationRef(
            id=self.destination_loc.id, code=self.destination_loc.code, name=self.destination_loc.name,
            country_code="PG", currency_code="PGK",
        )

        shipment = ShipmentDetails(
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="DAP",
            payment_term="PREPAID",
            commodity_code="GCR",
            is_dangerous_goods=False,
            pieces=[Piece(pieces=1, length_cm=0, width_cm=0, height_cm=0, gross_weight_kg=100)],
            service_scope="A2A",
            origin_location=origin_ref,
            destination_location=dest_ref,
        )

        quote_input = QuoteInput(
            customer_id=self.customer.id,
            contact_id=self.contact.id,
            output_currency="PGK",
            buy_currency="USD",
            agent_id=None,
            carrier_id=None,
            quote_date=date.today(),
            shipment=shipment,
            overrides=[],
            spot_rates={}
        )

        # Calculate using V4 adapter for SPOT
        adapter = PricingServiceV4Adapter(quote_input, spot_envelope_id=spe.id)
        result = adapter.calculate_charges()
        
        # Verify FX details
        fx = adapter._audit_metadata.get("fx_audit", {})
        self.assertAlmostEqual(Decimal(fx["base_rate"]), Decimal("0.235500"))
        self.assertAlmostEqual(Decimal(fx["caf_percent"]), Decimal("0.05"))
        self.assertAlmostEqual(Decimal(fx["effective_rate_after_caf"]), Decimal("0.223725"))
        
        # Verify line level calculations
        lines = result.lines
        freight_line = next(line for line in lines if line.product_code == "IMP-FRT-AIR")
        
        # Cost PGK: 680 USD / 0.223725 = 3,039.45 PGK
        self.assertAlmostEqual(Decimal(freight_line.cost_pgk), Decimal("3039.45"), places=2)
        # Sell PGK: 3039.45 * 1.20 = 3,647.34 PGK (3647.33 after unrounded math)
        self.assertAlmostEqual(Decimal(freight_line.sell_pgk), Decimal("3647.33"), places=2)
        
        # Margin PGK: 3647.34 - 3039.45 = 607.89 PGK
        margin_amount = freight_line.sell_pgk - freight_line.cost_pgk
        self.assertAlmostEqual(margin_amount, Decimal("607.89"), places=2)
        # Margin Percent: 607.89 / 3647.34 = 16.67%
        margin_percent = (margin_amount / freight_line.sell_pgk) * 100
        self.assertAlmostEqual(margin_percent, Decimal("16.67"), places=2)
