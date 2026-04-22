from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, Currency
from core.tests.helpers import create_location
from parties.models import Company, Contact
from pricing_v4.models import Agent, ImportCOGS, ProductCode


class QuoteComputeSelectorValidationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="selector-validation",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(self.user)

        aud = Currency.objects.create(code="AUD", name="Australian Dollar", minor_units=2)
        pgk = Currency.objects.create(code="PGK", name="Papua New Guinean Kina", minor_units=2)
        au = Country.objects.create(code="AU", name="Australia", currency=aud)
        pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)

        self.origin = create_location(code="SYD", name="Sydney", country=au, is_active=True)
        self.destination = create_location(code="POM", name="Port Moresby", country=pg, is_active=True)
        self.customer = Company.objects.create(name="Selector Customer", company_type="CUSTOMER", is_customer=True)
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Sel",
            last_name="Ector",
            email="selector@example.com",
        )
        self.agent_a = Agent.objects.create(
            code="VAL-AG-A",
            name="Validation Agent A",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.agent_b = Agent.objects.create(
            code="VAL-AG-B",
            name="Validation Agent B",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.freight_pc = ProductCode.objects.create(
            id=2660,
            code="IMP-FRT-VALIDATION",
            description="Import Freight Validation",
            domain="IMPORT",
            category="FREIGHT",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)

    def _payload(self, **overrides):
        payload = {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": "A2A",
            "origin_location_id": str(self.origin.id),
            "destination_location_id": str(self.destination.id),
            "incoterm": "EXW",
            "payment_term": "COLLECT",
            "dimensions": [
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "25",
                    "package_type": "Box",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_quote_compute_requires_buy_currency_when_import_cogs_are_multicurrency(self):
        for currency, amount in [("AUD", "4.80"), ("PGK", "12.50")]:
            ImportCOGS.objects.create(
                product_code=self.freight_pc,
                origin_airport="SYD",
                destination_airport="POM",
                agent=self.agent_a,
                currency=currency,
                rate_per_kg=Decimal(amount),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "RATE_SELECTION_MISSING_DIMENSION")
        self.assertEqual(response.data["component"], "FREIGHT")
        self.assertEqual(response.data["missing_dimensions"], ["buy_currency"])
        self.assertEqual(response.data["resolved_dimensions"]["agent_id"], self.agent_a.id)
        self.assertIsNone(response.data["resolved_dimensions"]["buy_currency"])

    def test_quote_compute_requires_agent_when_counterparty_specific_import_cogs_exist(self):
        for agent in [self.agent_a, self.agent_b]:
            ImportCOGS.objects.create(
                product_code=self.freight_pc,
                origin_airport="SYD",
                destination_airport="POM",
                agent=agent,
                currency="AUD",
                rate_per_kg=Decimal("4.80"),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "RATE_SELECTION_MISSING_DIMENSION")
        self.assertEqual(response.data["component"], "FREIGHT")
        self.assertEqual(response.data["missing_dimensions"], ["agent_id"])
        self.assertEqual(response.data["resolved_dimensions"]["buy_currency"], "AUD")
        self.assertIsNone(response.data["resolved_dimensions"]["agent_id"])

    def test_quote_compute_allows_component_level_resolution_when_global_path_is_not_shared(self):
        origin_pc = ProductCode.objects.create(
            id=2661,
            code="IMP-ORIGIN-HANDLING-VALIDATION",
            description="Import Origin Validation",
            domain="IMPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        destination_pc = ProductCode.objects.create(
            id=2662,
            code="IMP-CARTAGE-DEST-VALIDATION",
            description="Import Destination Validation",
            domain="IMPORT",
            category="CARTAGE",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )

        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_a,
            currency="AUD",
            rate_per_kg=Decimal("4.80"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ImportCOGS.objects.create(
            product_code=origin_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_a,
            currency="AUD",
            rate_per_shipment=Decimal("60.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ImportCOGS.objects.create(
            product_code=destination_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_b,
            currency="AUD",
            rate_per_shipment=Decimal("95.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._payload(service_scope="D2D"),
            format="json",
        )

        self.assertNotEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotEqual(response.data.get("error_code"), "RATE_RESOLUTION_MISSING_COVERAGE")
