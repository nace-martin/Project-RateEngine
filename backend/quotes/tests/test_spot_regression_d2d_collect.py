from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from rest_framework import status
from parties.models import Company
from core.models import Country
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
