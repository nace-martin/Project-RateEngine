from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from core.commodity import COMMODITY_CODE_AVI, COMMODITY_CODE_DG, DEFAULT_COMMODITY_CODE
from core.dataclasses import CalculatedTotals, QuoteCharges
from core.models import Country, Currency, FxSnapshot, Location, Policy
from parties.models import Company, Contact
from pricing_v4.models import CommodityChargeRule, ProductCode
from quotes.models import Quote
from quotes.schemas import QuoteComputeRequest
from quotes.views.calculation import QuoteComputeV3APIView, _classify_shipment_type


class QuoteCommoditySchemaTests(TestCase):
    def test_quote_compute_request_defaults_to_general_cargo(self):
        payload = QuoteComputeRequest(
            customer_id=uuid4(),
            contact_id=uuid4(),
            mode="AIR",
            service_scope="D2D",
            origin_location_id=uuid4(),
            destination_location_id=uuid4(),
            incoterm="DAP",
            payment_term="PREPAID",
            dimensions=[
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "10",
                }
            ],
        )

        self.assertEqual(payload.commodity_code, DEFAULT_COMMODITY_CODE)
        self.assertFalse(payload.is_dangerous_goods)

    def test_quote_compute_request_promotes_legacy_dg_flag(self):
        payload = QuoteComputeRequest(
            customer_id=uuid4(),
            contact_id=uuid4(),
            mode="AIR",
            service_scope="D2D",
            origin_location_id=uuid4(),
            destination_location_id=uuid4(),
            incoterm="DAP",
            payment_term="PREPAID",
            is_dangerous_goods=True,
            dimensions=[
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "10",
                }
            ],
        )

        self.assertEqual(payload.commodity_code, COMMODITY_CODE_DG)
        self.assertTrue(payload.is_dangerous_goods)


class QuoteCommodityPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(
            username="commodity_tester",
            password="pass123",
            email="commodity_tester@example.com",
        )
        cls.customer = Company.objects.create(name="Commodity Customer")
        cls.contact = Contact.objects.create(
            company=cls.customer,
            first_name="Ava",
            last_name="Loader",
            email="ava.loader@example.com",
        )
        aud = Currency.objects.create(code="AUD", name="Australian Dollar")
        pgk = Currency.objects.create(code="PGK", name="Papua New Guinean Kina")
        au = Country.objects.create(code="AU", name="Australia", currency=aud)
        pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)
        cls.origin = Location.objects.create(code="SYD", name="Sydney", country=au, is_active=True)
        cls.destination = Location.objects.create(code="POM", name="Port Moresby", country=pg, is_active=True)
        cls.fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="TEST",
            rates={"AUDPGK": "2.50"},
            caf_percent=Decimal("0.05"),
            fx_buffer_percent=Decimal("0.02"),
        )
        cls.policy = Policy.objects.create(
            name="Commodity Test Policy",
            caf_import_pct=Decimal("0.05"),
            caf_export_pct=Decimal("0.10"),
            margin_pct=Decimal("0.20"),
            effective_from=timezone.now(),
            effective_to=timezone.now() + timedelta(days=30),
            is_active=True,
        )

    def _build_request(self):
        request = APIRequestFactory().post("/api/v3/quotes/compute/")
        request.user = self.user
        return request

    def test_build_quote_input_carries_commodity_code(self):
        payload = QuoteComputeRequest(
            customer_id=self.customer.id,
            contact_id=self.contact.id,
            mode="AIR",
            service_scope="A2D",
            origin_location_id=self.origin.id,
            destination_location_id=self.destination.id,
            incoterm="DAP",
            payment_term="PREPAID",
            commodity_code=COMMODITY_CODE_AVI,
            dimensions=[
                {
                    "pieces": 2,
                    "length_cm": "20",
                    "width_cm": "30",
                    "height_cm": "40",
                    "gross_weight_kg": "60",
                }
            ],
        )

        shipment_type = _classify_shipment_type(payload.mode, self.origin, self.destination)
        quote_input = QuoteComputeV3APIView()._build_quote_input(
            payload,
            shipment_type,
            self.origin,
            self.destination,
        )

        self.assertEqual(quote_input.shipment.commodity_code, COMMODITY_CODE_AVI)
        self.assertFalse(quote_input.shipment.is_dangerous_goods)

    def test_save_quote_persists_commodity_code_and_payload(self):
        payload = QuoteComputeRequest(
            customer_id=self.customer.id,
            contact_id=self.contact.id,
            mode="AIR",
            service_scope="A2D",
            origin_location_id=self.origin.id,
            destination_location_id=self.destination.id,
            incoterm="DAP",
            payment_term="PREPAID",
            commodity_code=COMMODITY_CODE_AVI,
            dimensions=[
                {
                    "pieces": 2,
                    "length_cm": "20",
                    "width_cm": "30",
                    "height_cm": "40",
                    "gross_weight_kg": "60",
                }
            ],
        )
        shipment_type = _classify_shipment_type(payload.mode, self.origin, self.destination)
        charges = QuoteCharges(
            lines=[],
            totals=CalculatedTotals(
                total_cost_pgk=Decimal("0.00"),
                total_sell_pgk=Decimal("0.00"),
                total_sell_pgk_incl_gst=Decimal("0.00"),
                total_sell_fcy=Decimal("0.00"),
                total_sell_fcy_incl_gst=Decimal("0.00"),
                total_sell_fcy_currency="PGK",
                has_missing_rates=False,
            ),
        )

        quote = QuoteComputeV3APIView()._save_quote_v3(
            request=self._build_request(),
            validated_data=payload,
            shipment_type=shipment_type,
            charges=charges,
            snapshot=self.fx_snapshot,
            policy=self.policy,
            output_currency="PGK",
            initial_status=Quote.Status.DRAFT,
        )

        version = quote.versions.get(version_number=1)
        self.assertEqual(quote.commodity_code, COMMODITY_CODE_AVI)
        self.assertFalse(quote.is_dangerous_goods)
        self.assertEqual(quote.request_details_json["commodity_code"], COMMODITY_CODE_AVI)
        self.assertEqual(version.payload_json["commodity_code"], COMMODITY_CODE_AVI)


class QuoteCommodityAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="commodity_api_tester",
            password="pass123",
            email="commodity_api_tester@example.com",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("quotes:quote-compute-v3")
        self.customer = Company.objects.create(name="Commodity API Customer")
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Ivy",
            last_name="Consignee",
            email="ivy.consignee@example.com",
        )
        aud = Currency.objects.create(code="AUD", name="Australian Dollar")
        pgk = Currency.objects.create(code="PGK", name="Papua New Guinean Kina")
        au = Country.objects.create(code="AU", name="Australia", currency=aud)
        pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)
        self.origin = Location.objects.create(code="SYD", name="Sydney", country=au, is_active=True)
        self.destination = Location.objects.create(code="POM", name="Port Moresby", country=pg, is_active=True)

    def test_standard_compute_blocks_dg_when_sent_as_commodity_code(self):
        response = self.client.post(
            self.url,
            {
                "customer_id": str(self.customer.id),
                "contact_id": str(self.contact.id),
                "mode": "AIR",
                "service_scope": "D2D",
                "origin_location_id": str(self.origin.id),
                "destination_location_id": str(self.destination.id),
                "incoterm": "DAP",
                "payment_term": "PREPAID",
                "commodity_code": COMMODITY_CODE_DG,
                "dimensions": [
                    {
                        "pieces": 1,
                        "length_cm": "10",
                        "width_cm": "10",
                        "height_cm": "10",
                        "gross_weight_kg": "10",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["detail"],
            "Dangerous Goods (DG) shipments are not yet supported.",
        )

    def test_standard_compute_blocks_manual_only_commodity_rule_with_spot_trigger(self):
        CommodityChargeRule.objects.create(
            shipment_type=Quote.ShipmentType.IMPORT,
            service_scope="A2D",
            commodity_code=COMMODITY_CODE_AVI,
            product_code=ProductCode.objects.create(
                id=2987,
                code="IMP-AVI-MANUAL-API",
                description="Import AVI manual only",
                domain="IMPORT",
                category="HANDLING",
                is_gst_applicable=True,
                gl_revenue_code="4100",
                gl_cost_code="5100",
                default_unit="SHIPMENT",
            ),
            leg="DESTINATION",
            trigger_mode="REQUIRES_MANUAL",
            effective_from=timezone.now().date() - timedelta(days=1),
            effective_to=timezone.now().date() + timedelta(days=30),
        )

        response = self.client.post(
            self.url,
            {
                "customer_id": str(self.customer.id),
                "contact_id": str(self.contact.id),
                "mode": "AIR",
                "service_scope": "A2D",
                "origin_location_id": str(self.origin.id),
                "destination_location_id": str(self.destination.id),
                "incoterm": "DAP",
                "payment_term": "PREPAID",
                "commodity_code": COMMODITY_CODE_AVI,
                "dimensions": [
                    {
                        "pieces": 1,
                        "length_cm": "10",
                        "width_cm": "10",
                        "height_cm": "10",
                        "gross_weight_kg": "10",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertEqual(payload["spot_trigger"]["code"], "COMMODITY_REQUIRES_MANUAL")
        self.assertEqual(
            payload["spot_trigger"]["manual_required_product_codes"],
            ["IMP-AVI-MANUAL-API"],
        )
