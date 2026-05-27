from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from rest_framework import status
from parties.models import Company
from core.models import Country, Location
from core.tests.helpers import create_location
from quotes.models import Quote
from pricing_v4.models import ProductCode, LocalSellRate
import json

User = get_user_model()

class SPOTRegressionD2DCollectTests(APITestCase):
    """
    Regression tests for IMPORT D2D COLLECT scenarios.
    """
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Company.objects.create(name="Seed Customer Pty Ltd")
        
        # Create Countries
        self.cn = Country.objects.create(code="CN", name="China")
        self.pg = Country.objects.create(code="PG", name="Papua New Guinea")
        
        # CAN -> POM
        self.origin = create_location(code="CAN", name="Guangzhou", country=self.cn)
        self.destination = create_location(code="POM", name="Port Moresby", country=self.pg)

        # Create a ProductCode for Destination Local
        pc = ProductCode.objects.create(
            id=2020, 
            code="DEST-LOCAL", 
            category="LOCAL", 
            description="Dest Local", 
            is_gst_applicable=True, 
            domain="IMPORT"
        )
        
        # Create a LocalSellRate for POM IMPORT
        LocalSellRate.objects.create(
            product_code=pc,
            location="POM",
            direction="IMPORT",
            currency="PGK",
            amount=100.0,
            valid_from="2025-01-01",
            valid_until="2026-12-31"
        )

    def test_create_spe_import_d2d_collect_safe(self):
        """
        Verify that creating an SPE for IMPORT D2D COLLECT with missing FREIGHT/ORIGIN_LOCAL
        but covered DESTINATION_LOCAL does not 500.
        """
        # Create a real quote
        quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="IMPORT",
            origin_location=self.origin,
            destination_location=self.destination,
            status="DRAFT",
            service_scope="D2D",
            payment_term="COLLECT",
            commodity_code="GCR",
            created_by=self.user
        )

        # 1. Evaluate trigger (simulate frontend)
        eval_url = "/api/v3/spot/evaluate-trigger/"
        eval_payload = {
            "origin_country": "CN",
            "destination_country": "PG",
            "origin_airport": "CAN",
            "destination_airport": "POM",
            "service_scope": "D2D",
            "payment_term": "COLLECT",
            "commodity": "GCR",
            "quote_id": str(quote.id)
        }
        eval_response = self.client.post(eval_url, eval_payload, format="json")
        self.assertEqual(eval_response.status_code, status.HTTP_200_OK)
        trigger_data = eval_response.json()
        self.assertTrue(trigger_data["is_spot_required"])
        
        # 2. Create SPE
        url = "/api/v3/spot/envelopes/"
        payload = {
            "quote_id": str(quote.id),
            "shipment_context": {
                "origin_country": "CN",
                "destination_country": "PG",
                "origin_code": "CAN",
                "destination_code": "POM",
                "customer_name": "Seed Customer Pty Ltd",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "d2d",
                "payment_term": "collect",
                "missing_components": trigger_data["trigger"]["missing_components"]
            },
            "charges": [],
            "trigger_code": trigger_data["trigger"]["code"],
            "trigger_text": trigger_data["trigger"]["text"]
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["shipment"]["payment_term"], "COLLECT")
        self.assertIn("FREIGHT", data["shipment"]["missing_components"])
        self.assertIn("ORIGIN_LOCAL", data["shipment"]["missing_components"])
        self.assertNotIn("DESTINATION_LOCAL", data["shipment"]["missing_components"])

    def test_import_bne_pom_d2d_collect_all_present_no_spot(self):
        """
        D2D, COLLECT Import BNE -> POM with all components present in DB.
        Expected: SPOT must NOT trigger.
        """
        # Create AU and BNE
        au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia"})[0]
        bne = create_location(code="BNE", name="Brisbane", country=au)
        
        # ProductCodes
        pc_frt, _ = ProductCode.objects.get_or_create(
            id=2001,
            defaults={"code": "IMP-FRT-AIR", "category": "FREIGHT", "description": "Freight", "domain": "IMPORT", "is_gst_applicable": True}
        )
        pc_origin, _ = ProductCode.objects.get_or_create(
            id=2050,
            defaults={"code": "IMP-PICKUP", "category": "CARTAGE", "description": "Origin Pickup", "domain": "IMPORT", "is_gst_applicable": True}
        )
        pc_dest, _ = ProductCode.objects.get_or_create(
            id=2060,
            defaults={"code": "IMP-CARTAGE-DEST", "category": "CARTAGE", "description": "Dest Delivery", "domain": "IMPORT", "is_gst_applicable": True}
        )
        
        # Seed buy/sell rows
        from pricing_v4.models import ImportCOGS, LocalCOGSRate, LocalSellRate, Agent
        
        agent, _ = Agent.objects.get_or_create(
            code="EFM-AU",
            defaults={"name": "EFM Australia", "country_code": "AU", "agent_type": "ORIGIN"}
        )

        ImportCOGS.objects.get_or_create(
            product_code=pc_frt,
            origin_airport="BNE",
            destination_airport="POM",
            currency="AUD",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_per_kg": 5.0}
        )
        LocalCOGSRate.objects.get_or_create(
            product_code=pc_origin,
            location="BNE",
            direction="IMPORT",
            currency="AUD",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 100.0}
        )
        LocalCOGSRate.objects.get_or_create(
            product_code=pc_dest,
            location="POM",
            direction="IMPORT",
            currency="PGK",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 150.0}
        )
        LocalSellRate.objects.get_or_create(
            product_code=pc_dest,
            location="POM",
            direction="IMPORT",
            currency="PGK",
            payment_term="COLLECT",
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 200.0}
        )
        
        # Create quote
        quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="IMPORT",
            origin_location=bne,
            destination_location=self.destination,
            status="DRAFT",
            service_scope="D2D",
            payment_term="COLLECT",
            commodity_code="GCR",
            created_by=self.user
        )
        
        eval_url = "/api/v3/spot/evaluate-trigger/"
        eval_payload = {
            "origin_country": "AU",
            "destination_country": "PG",
            "origin_airport": "BNE",
            "destination_airport": "POM",
            "service_scope": "D2D",
            "payment_term": "COLLECT",
            "commodity": "GCR",
            "quote_id": str(quote.id)
        }
        response = self.client.post(eval_url, eval_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertFalse(data["is_spot_required"])
        self.assertIn("debug_audit", data)

    def test_import_bne_pom_d2d_collect_origin_missing_spot_origin_only(self):
        """
        D2D, COLLECT Import BNE -> POM with origin local missing.
        Expected: SPOT triggers with ORIGIN_LOCAL in missing_components.
        """
        # Create AU and BNE
        au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia"})[0]
        bne = create_location(code="BNE", name="Brisbane", country=au)
        
        # ProductCodes
        pc_frt, _ = ProductCode.objects.get_or_create(
            id=2001,
            defaults={"code": "IMP-FRT-AIR", "category": "FREIGHT", "description": "Freight", "domain": "IMPORT", "is_gst_applicable": True}
        )
        pc_dest, _ = ProductCode.objects.get_or_create(
            id=2060,
            defaults={"code": "IMP-CARTAGE-DEST", "category": "CARTAGE", "description": "Dest Delivery", "domain": "IMPORT", "is_gst_applicable": True}
        )
        
        # Seed freight and destination charges, but NOT origin
        from pricing_v4.models import ImportCOGS, LocalCOGSRate, LocalSellRate, Agent
        
        agent, _ = Agent.objects.get_or_create(
            code="EFM-AU",
            defaults={"name": "EFM Australia", "country_code": "AU", "agent_type": "ORIGIN"}
        )

        ImportCOGS.objects.get_or_create(
            product_code=pc_frt,
            origin_airport="BNE",
            destination_airport="POM",
            currency="AUD",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_per_kg": 5.0}
        )
        LocalCOGSRate.objects.get_or_create(
            product_code=pc_dest,
            location="POM",
            direction="IMPORT",
            currency="PGK",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 150.0}
        )
        LocalSellRate.objects.get_or_create(
            product_code=pc_dest,
            location="POM",
            direction="IMPORT",
            currency="PGK",
            payment_term="COLLECT",
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 200.0}
        )
        
        # Ensure BNE LocalCOGSRate for origin pickup is NOT in the database
        LocalCOGSRate.objects.filter(location="BNE", direction="IMPORT").delete()
        
        # Create quote
        quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="IMPORT",
            origin_location=bne,
            destination_location=self.destination,
            status="DRAFT",
            service_scope="D2D",
            payment_term="COLLECT",
            commodity_code="GCR",
            created_by=self.user
        )
        
        eval_url = "/api/v3/spot/evaluate-trigger/"
        eval_payload = {
            "origin_country": "AU",
            "destination_country": "PG",
            "origin_airport": "BNE",
            "destination_airport": "POM",
            "service_scope": "D2D",
            "payment_term": "COLLECT",
            "commodity": "GCR",
            "quote_id": str(quote.id)
        }
        response = self.client.post(eval_url, eval_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertTrue(data["is_spot_required"])
        self.assertEqual(data["trigger"]["missing_components"], ["ORIGIN_LOCAL"])

    def test_import_bne_pom_d2d_collect_destination_missing_spot_destination_only(self):
        """
        D2D, COLLECT Import BNE -> POM with destination local missing.
        Expected: SPOT triggers with DESTINATION_LOCAL in missing_components.
        """
        # Create AU and BNE
        au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia"})[0]
        bne = create_location(code="BNE", name="Brisbane", country=au)
        
        # ProductCodes
        pc_frt, _ = ProductCode.objects.get_or_create(
            id=2001,
            defaults={"code": "IMP-FRT-AIR", "category": "FREIGHT", "description": "Freight", "domain": "IMPORT", "is_gst_applicable": True}
        )
        pc_origin, _ = ProductCode.objects.get_or_create(
            id=2050,
            defaults={"code": "IMP-PICKUP", "category": "CARTAGE", "description": "Origin Pickup", "domain": "IMPORT", "is_gst_applicable": True}
        )
        
        # Seed freight and origin charges, but NOT destination
        from pricing_v4.models import ImportCOGS, LocalCOGSRate, LocalSellRate, Agent
        
        agent, _ = Agent.objects.get_or_create(
            code="EFM-AU",
            defaults={"name": "EFM Australia", "country_code": "AU", "agent_type": "ORIGIN"}
        )

        ImportCOGS.objects.get_or_create(
            product_code=pc_frt,
            origin_airport="BNE",
            destination_airport="POM",
            currency="AUD",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_per_kg": 5.0}
        )
        LocalCOGSRate.objects.get_or_create(
            product_code=pc_origin,
            location="BNE",
            direction="IMPORT",
            currency="AUD",
            agent=agent,
            valid_from="2025-01-01",
            valid_until="2026-12-31",
            defaults={"rate_type": "FIXED", "amount": 100.0}
        )
        
        # Ensure POM LocalCOGSRate / LocalSellRate for destination is NOT in the database
        LocalCOGSRate.objects.filter(location="POM", direction="IMPORT").delete()
        LocalSellRate.objects.filter(location="POM", direction="IMPORT").delete()
        
        # Create quote
        quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="IMPORT",
            origin_location=bne,
            destination_location=self.destination,
            status="DRAFT",
            service_scope="D2D",
            payment_term="COLLECT",
            commodity_code="GCR",
            created_by=self.user
        )
        
        eval_url = "/api/v3/spot/evaluate-trigger/"
        eval_payload = {
            "origin_country": "AU",
            "destination_country": "PG",
            "origin_airport": "BNE",
            "destination_airport": "POM",
            "service_scope": "D2D",
            "payment_term": "COLLECT",
            "commodity": "GCR",
            "quote_id": str(quote.id)
        }
        response = self.client.post(eval_url, eval_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertTrue(data["is_spot_required"])
        self.assertEqual(data["trigger"]["missing_components"], ["DESTINATION_LOCAL"])
