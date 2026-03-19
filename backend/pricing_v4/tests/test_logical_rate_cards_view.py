from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from pricing_v4.models import (
    Agent,
    DomesticSellRate,
    ExportSellRate,
    ImportCOGS,
    LocalSellRate,
    ProductCode,
)


class LogicalRateCardsViewTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            username="manager",
            password="testpass123",
            role="manager",
        )
        self.sales = user_model.objects.create_user(
            username="sales",
            password="testpass123",
            role="sales",
        )

        self.export_freight = ProductCode.objects.create(
            id=1001,
            code="EXP-FRT-TEST",
            description="Export Freight Test",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4000",
            gl_cost_code="5000",
        )
        self.export_local = ProductCode.objects.create(
            id=1002,
            code="EXP-DOC-TEST",
            description="Export Documentation Test",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4001",
            gl_cost_code="5001",
        )
        self.import_freight = ProductCode.objects.create(
            id=2001,
            code="IMP-FRT-TEST",
            description="Import Freight Test",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code="4100",
            gl_cost_code="5100",
        )
        self.import_local = ProductCode.objects.create(
            id=2002,
            code="IMP-CLEAR-TEST",
            description="Import Clearance Test",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_CLEARANCE,
            is_gst_applicable=True,
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code="4101",
            gl_cost_code="5101",
        )
        self.domestic_freight = ProductCode.objects.create(
            id=3001,
            code="DOM-FRT-TEST",
            description="Domestic Freight Test",
            domain=ProductCode.DOMAIN_DOMESTIC,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code="4200",
            gl_cost_code="5200",
        )

        valid_from = date(2026, 1, 1)
        valid_until = date(2026, 12, 31)

        ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_kg="7.50",
            valid_from=valid_from,
            valid_until=valid_until,
        )
        LocalSellRate.objects.create(
            product_code=self.export_local,
            location="POM",
            direction="EXPORT",
            payment_term="COLLECT",
            currency="PGK",
            rate_type="SHIPMENT",
            amount="35.00",
            valid_from=valid_from,
            valid_until=valid_until,
        )
        LocalSellRate.objects.create(
            product_code=self.import_local,
            location="POM",
            direction="IMPORT",
            payment_term="COLLECT",
            currency="PGK",
            rate_type="SHIPMENT",
            amount="85.00",
            valid_from=valid_from,
            valid_until=valid_until,
        )

        agent = Agent.objects.create(code="EFMAU", name="EFM AU", country_code="AU", agent_type="ORIGIN")
        ImportCOGS.objects.create(
            product_code=self.import_freight,
            origin_airport="SYD",
            destination_airport="POM",
            agent=agent,
            currency="AUD",
            rate_per_kg="4.20",
            valid_from=valid_from,
            valid_until=valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=self.domestic_freight,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg="7.30",
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def test_manager_sees_v4_architecture_cards(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/v4/rate-cards/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)

        import_collect = next(card for card in response.data if card["id"] == "import-collect-a2d")
        self.assertEqual(
            import_collect["source_tables"],
            ["LocalSellRate", "ImportCOGS"],
        )
        self.assertIn("Mixed: explicit local sell + cost-plus lane pricing", import_collect["pricing_model"])
        self.assertTrue(any(line["source_table"] == "LocalSellRate" for line in import_collect["lines"]))
        self.assertTrue(any(line["source_table"] == "ImportCOGS" for line in import_collect["lines"]))

        export_collect = next(card for card in response.data if card["id"] == "export-collect-d2a")
        self.assertIn("POM", export_collect["coverage"])
        self.assertIn("POM->BNE", export_collect["coverage"])

    def test_sales_user_cannot_access_logical_rate_cards(self):
        self.client.force_authenticate(self.sales)

        response = self.client.get("/api/v4/rate-cards/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
