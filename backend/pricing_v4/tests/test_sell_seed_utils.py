from datetime import date
from decimal import Decimal

from django.test import TestCase

from pricing_v4.management.commands._sell_seed_utils import (
    seed_export_sell_rate,
    seed_import_sell_rate,
)
from pricing_v4.models import ExportSellRate, ImportSellRate, LocalSellRate, ProductCode


class SellSeedUtilsTests(TestCase):
    def setUp(self):
        self.export_freight = ProductCode.objects.create(
            id=1001,
            code="EXP-FRT-AIR-TEST",
            description="Export Freight Test",
            domain="EXPORT",
            category="FREIGHT",
            is_gst_applicable=False,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        self.export_local = ProductCode.objects.create(
            id=1010,
            code="EXP-DOC-TEST",
            description="Export Documentation Test",
            domain="EXPORT",
            category="DOCUMENTATION",
            is_gst_applicable=False,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        self.export_pickup = ProductCode.objects.create(
            id=1050,
            code="EXP-PICKUP-TEST",
            description="Export Pickup Test",
            domain="EXPORT",
            category="CARTAGE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        self.export_pickup_fsc = ProductCode.objects.create(
            id=1060,
            code="EXP-FSC-PICKUP-TEST",
            description="Export Pickup Fuel Surcharge Test",
            domain="EXPORT",
            category="SURCHARGE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="PERCENT",
        )
        self.export_destination_local = ProductCode.objects.create(
            id=1080,
            code="EXP-CLEAR-DEST-TEST",
            description="Export Destination Clearance Test",
            domain="EXPORT",
            category="CLEARANCE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        self.import_local = ProductCode.objects.create(
            id=2010,
            code="IMP-CLEAR-TEST",
            description="Import Clearance Test",
            domain="IMPORT",
            category="CLEARANCE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        self.import_cartage = ProductCode.objects.create(
            id=2050,
            code="IMP-CARTAGE-DEST-TEST",
            description="Import Cartage Test",
            domain="IMPORT",
            category="CARTAGE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        self.import_cartage_fsc = ProductCode.objects.create(
            id=2060,
            code="IMP-FSC-CARTAGE-DEST-TEST",
            description="Import Cartage FSC Test",
            domain="IMPORT",
            category="SURCHARGE",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="PERCENT",
        )

    def test_export_local_seed_uses_local_sell_rate(self):
        result = seed_export_sell_rate(
            product_code=self.export_local,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            rate_per_shipment=Decimal("50.00"),
            payment_term="PREPAID",
        )

        self.assertEqual(result.table_name, "LocalSellRate")
        self.assertEqual(ExportSellRate.objects.count(), 0)
        local = LocalSellRate.objects.get()
        self.assertEqual(local.location, "POM")
        self.assertEqual(local.direction, "EXPORT")
        self.assertEqual(local.payment_term, "PREPAID")
        self.assertEqual(local.amount, Decimal("50.00"))

    def test_export_destination_local_seed_uses_destination_station(self):
        result = seed_export_sell_rate(
            product_code=self.export_destination_local,
            origin_airport="POM",
            destination_airport="SIN",
            currency="USD",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            rate_per_shipment=Decimal("85.00"),
            payment_term="PREPAID",
        )

        self.assertEqual(result.table_name, "LocalSellRate")
        local = LocalSellRate.objects.get(product_code=self.export_destination_local)
        self.assertEqual(local.location, "SIN")
        self.assertEqual(local.direction, "EXPORT")
        self.assertEqual(local.payment_term, "PREPAID")
        self.assertEqual(local.amount, Decimal("85.00"))

    def test_export_freight_seed_stays_lane_based(self):
        result = seed_export_sell_rate(
            product_code=self.export_freight,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            rate_per_kg=Decimal("7.90"),
        )

        self.assertEqual(result.table_name, "ExportSellRate")
        self.assertEqual(LocalSellRate.objects.count(), 0)
        self.assertEqual(ExportSellRate.objects.count(), 1)

    def test_export_percent_local_seed_sets_percent_base_on_local_sell_rate(self):
        result = seed_export_sell_rate(
            product_code=self.export_pickup_fsc,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            percent_rate=Decimal("10.00"),
            payment_term="PREPAID",
            percent_of_product_code=self.export_pickup,
        )

        self.assertEqual(result.table_name, "LocalSellRate")
        local = LocalSellRate.objects.get(product_code=self.export_pickup_fsc)
        self.assertEqual(local.rate_type, "PERCENT")
        self.assertEqual(local.amount, Decimal("10.00"))
        self.assertEqual(local.percent_of_product_code, self.export_pickup)

    def test_import_local_seed_uses_local_sell_rate(self):
        result = seed_import_sell_rate(
            product_code=self.import_local,
            origin_airport="SYD",
            destination_airport="POM",
            currency="PGK",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            rate_per_shipment=Decimal("300.00"),
            payment_term="COLLECT",
        )

        self.assertEqual(result.table_name, "LocalSellRate")
        self.assertEqual(ImportSellRate.objects.count(), 0)
        local = LocalSellRate.objects.get()
        self.assertEqual(local.location, "POM")
        self.assertEqual(local.direction, "IMPORT")
        self.assertEqual(local.payment_term, "COLLECT")

    def test_import_percent_local_seed_sets_percent_base_on_local_sell_rate(self):
        result = seed_import_sell_rate(
            product_code=self.import_cartage_fsc,
            origin_airport="SYD",
            destination_airport="POM",
            currency="AUD",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            percent_rate=Decimal("10.00"),
            payment_term="PREPAID",
            percent_of_product_code=self.import_cartage,
        )

        self.assertEqual(result.table_name, "LocalSellRate")
        local = LocalSellRate.objects.get(product_code=self.import_cartage_fsc)
        self.assertEqual(local.rate_type, "PERCENT")
        self.assertEqual(local.percent_of_product_code, self.import_cartage)
