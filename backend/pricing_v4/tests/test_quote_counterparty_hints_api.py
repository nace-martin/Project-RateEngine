from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from pricing_v4.models import Agent, Carrier, DomesticCOGS, ImportCOGS, ProductCode


class QuoteCounterpartyHintsAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="hints-manager",
            password="testpass123",
            role="manager",
        )
        self.sales = User.objects.create_user(
            username="hints-sales",
            password="testpass123",
            role="sales",
        )
        self.agent = Agent.objects.create(
            code="EFM-AU",
            name="EFM Australia",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.carrier = Carrier.objects.create(
            code="PX",
            name="Air Niugini",
            carrier_type="AIRLINE",
        )
        self.freight_pc = ProductCode.objects.create(
            id=2801,
            code="IMP-FRT-HINT",
            description="Import Freight Hint",
            domain="IMPORT",
            category="FREIGHT",
            default_unit="KG",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
        )
        self.origin_pc = ProductCode.objects.create(
            id=2810,
            code="IMP-DOC-ORIGIN-HINT",
            description="Import Origin Doc Hint",
            domain="IMPORT",
            category="DOCUMENTATION",
            default_unit="SHIPMENT",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
        )
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)

    def test_import_lane_with_only_agent_scoped_buy_rows_returns_agent_only_hints(self):
        for pc, rate_per_kg, rate_per_shipment in [
            (self.freight_pc, Decimal("4.80"), None),
            (self.origin_pc, None, Decimal("25.00")),
        ]:
            ImportCOGS.objects.create(
                product_code=pc,
                origin_airport="BNE",
                destination_airport="POM",
                agent=self.agent,
                currency="AUD",
                rate_per_kg=rate_per_kg,
                rate_per_shipment=rate_per_shipment,
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        self.client.force_authenticate(self.manager)
        response = self.client.get(
            "/api/v4/quote/counterparty-hints/",
            {
                "direction": "IMPORT",
                "service_scope": "D2D",
                "origin_airport": "BNE",
                "destination_airport": "POM",
                "buy_currency": "AUD",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_counterparty_types"], ["agent"])
        self.assertEqual(response.data["recommended_counterparty_type"], "agent")
        self.assertEqual(response.data["carriers"], [])
        self.assertEqual([agent["code"] for agent in response.data["agents"]], ["EFM-AU"])
        self.assertEqual(response.data["component_counterparty_types"]["FREIGHT"], ["agent"])
        self.assertEqual(response.data["component_counterparty_types"]["ORIGIN_LOCAL"], ["agent"])

    def test_currency_filter_excludes_counterparty_types_not_matching_buy_currency(self):
        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="BNE",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("4.80"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="BNE",
            destination_airport="POM",
            carrier=self.carrier,
            currency="USD",
            rate_per_kg=Decimal("5.10"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        self.client.force_authenticate(self.manager)
        response = self.client.get(
            "/api/v4/quote/counterparty-hints/",
            {
                "direction": "IMPORT",
                "service_scope": "A2A",
                "origin_airport": "BNE",
                "destination_airport": "POM",
                "buy_currency": "AUD",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_counterparty_types"], ["agent"])
        self.assertEqual(response.data["carriers"], [])

    def test_domestic_lane_with_single_pxdom_path_returns_one_hint_for_hidden_selector(self):
        domestic_agent = Agent.objects.create(
            code="PX-DOM",
            name="Air Niugini (Domestic)",
            country_code="PG",
            agent_type="CARRIER",
        )
        domestic_freight = ProductCode.objects.create(
            id=3801,
            code="DOM-FRT-HINT",
            description="Domestic Freight Hint",
            domain="DOMESTIC",
            category="FREIGHT",
            default_unit="KG",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
        )
        DomesticCOGS.objects.create(
            product_code=domestic_freight,
            origin_zone="POM",
            destination_zone="LAE",
            agent=domestic_agent,
            currency="PGK",
            rate_per_kg=Decimal("6.10"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        self.client.force_authenticate(self.manager)
        response = self.client.get(
            "/api/v4/quote/counterparty-hints/",
            {
                "direction": "DOMESTIC",
                "service_scope": "D2D",
                "origin_airport": "POM",
                "destination_airport": "LAE",
                "buy_currency": "PGK",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_counterparty_types"], ["agent"])
        self.assertEqual(response.data["recommended_counterparty_type"], "agent")
        self.assertEqual(response.data["carriers"], [])
        self.assertEqual([agent["code"] for agent in response.data["agents"]], ["PX-DOM"])

    def test_sales_users_cannot_access_counterparty_hints(self):
        self.client.force_authenticate(self.sales)
        response = self.client.get(
            "/api/v4/quote/counterparty-hints/",
            {
                "direction": "IMPORT",
                "service_scope": "A2A",
                "origin_airport": "BNE",
                "destination_airport": "POM",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
