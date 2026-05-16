from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import (
    Agent,
    DomesticCOGS,
    DomesticSellRate,
    ExportSellRate,
    LocalSellRate,
    ProductCode,
)
from pricing_v4.services.pricing_rate_scope import PricingRateScope, classify_pricing_rate_scope
from pricing_v4.services.rate_selector import (
    RateSelectionContext,
    select_export_sell_rate,
    select_local_sell_rate,
)


class PricingRateScopeClassificationTests(TestCase):
    def test_classifies_lane_local_and_unknown_products_without_db_lookup(self):
        cases = [
            (_product("EXP-FRT-AIR", "Export Air Freight", "EXPORT", "FREIGHT"), PricingRateScope.LANE),
            (_product("EXP-DOC", "Documentation Fee", "EXPORT", "DOCUMENTATION"), PricingRateScope.ORIGIN),
            (_product("EXP-DELIVERY-DEST", "Destination Delivery", "EXPORT", "CARTAGE"), PricingRateScope.DESTINATION),
            (_product("IMP-CLEAR", "Customs Clearance", "IMPORT", "CLEARANCE"), PricingRateScope.DESTINATION),
            (_product("IMP-PICKUP", "Pickup Charge", "IMPORT", "CARTAGE"), PricingRateScope.ORIGIN),
            (_product("DOM-DOC", "Documentation Fee", "DOMESTIC", "DOCUMENTATION"), PricingRateScope.LOCAL),
            (_product("DOM-MISC", "Domestic Miscellaneous", "DOMESTIC", "SPECIAL"), PricingRateScope.UNKNOWN),
        ]

        for product, expected_scope in cases:
            with self.subTest(product=product.code):
                self.assertEqual(classify_pricing_rate_scope(product), expected_scope)


class PricingRateScopeAuditCommandTests(TestCase):
    def setUp(self):
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)
        self.agent = Agent.objects.create(
            code="SCOPE-AG",
            name="Scope Audit Agent",
            country_code="PG",
            agent_type="ORIGIN",
        )
        self.export_doc = _create_product(1110, "EXP-DOC", "Documentation Fee", "EXPORT", "DOCUMENTATION")
        self.export_freight = _create_product(1101, "EXP-FRT-AIR", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        self.domestic_doc = _create_product(3310, "DOM-DOC", "Documentation Fee", "DOMESTIC", "DOCUMENTATION")
        self.unknown = _create_product(3399, "DOM-MISC", "Domestic Miscellaneous", "DOMESTIC", "SPECIAL")

    def test_audit_reports_scope_risks_without_changing_rows(self):
        ExportSellRate.objects.create(
            product_code=self.export_doc,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_shipment=Decimal("35.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ExportSellRate.objects.create(
            product_code=self.export_doc,
            origin_airport="POM",
            destination_airport="SYD",
            currency="PGK",
            rate_per_shipment=Decimal("35.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        DomesticCOGS.objects.create(
            product_code=self.domestic_doc,
            origin_zone="POM",
            destination_zone="LAE",
            agent=self.agent,
            currency="PGK",
            rate_per_shipment=Decimal("40.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        DomesticCOGS.objects.create(
            product_code=self.domestic_doc,
            origin_zone="POM",
            destination_zone="HGU",
            agent=self.agent,
            currency="PGK",
            rate_per_shipment=Decimal("40.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        LocalSellRate.objects.create(
            product_code=self.export_freight,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            rate_type="PER_KG",
            amount=Decimal("5.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=self.unknown,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_shipment=Decimal("9.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        before_counts = {
            "ExportSellRate": ExportSellRate.objects.count(),
            "DomesticCOGS": DomesticCOGS.objects.count(),
            "DomesticSellRate": DomesticSellRate.objects.count(),
            "LocalSellRate": LocalSellRate.objects.count(),
        }
        out = StringIO()

        call_command("audit_pricing_rate_scope", stdout=out)

        self.assertEqual(
            {
                "ExportSellRate": ExportSellRate.objects.count(),
                "DomesticCOGS": DomesticCOGS.objects.count(),
                "DomesticSellRate": DomesticSellRate.objects.count(),
                "LocalSellRate": LocalSellRate.objects.count(),
            },
            before_counts,
        )
        report = out.getvalue()
        self.assertIn("No rows were changed.", report)
        self.assertIn("Non-lane candidates stored in lane-shaped tables:", report)
        self.assertIn("ExportSellRate", report)
        self.assertIn("EXP-DOC", report)
        self.assertIn("DomesticCOGS", report)
        self.assertIn("DOM-DOC", report)
        self.assertIn("Lane candidates stored in local tables:", report)
        self.assertIn("LocalSellRate", report)
        self.assertIn("EXP-FRT-AIR", report)
        self.assertIn("Likely duplicate non-lane rows in lane-shaped tables:", report)
        self.assertIn("destinations=BNE, SYD", report)
        self.assertIn("UNKNOWN scope rows:", report)
        self.assertIn("DOM-MISC", report)


class PricingRateScopeSelectorRegressionTests(TestCase):
    def setUp(self):
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)
        self.valid_until_next = date.today() + timedelta(days=60)
        self.export_freight = _create_product(1101, "EXP-FRT-AIR", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        self.import_clear = _create_product(2220, "IMP-CLEAR", "Customs Clearance", "IMPORT", "CLEARANCE")

    def test_audit_helpers_do_not_change_selector_results(self):
        older = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_kg=Decimal("4.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until_next,
        )
        newer = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_kg=Decimal("4.50"),
            valid_from=date.today(),
            valid_until=self.valid_until_next,
        )
        local = LocalSellRate.objects.create(
            product_code=self.import_clear,
            location="POM",
            direction="IMPORT",
            payment_term="COLLECT",
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("300.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        for row in [older, newer, local]:
            classify_pricing_rate_scope(row)
        call_command("audit_pricing_rate_scope", stdout=StringIO())

        export_result = select_export_sell_rate(
            RateSelectionContext(
                product_code_id=self.export_freight.id,
                quote_date=date.today(),
                origin_airport="POM",
                destination_airport="BNE",
                currency="PGK",
            )
        )
        local_result = select_local_sell_rate(
            RateSelectionContext(
                product_code_id=self.import_clear.id,
                quote_date=date.today(),
                location="POM",
                direction="IMPORT",
                payment_term="COLLECT",
                currency="PGK",
            )
        )

        self.assertEqual(export_result.record.id, newer.id)
        self.assertNotEqual(export_result.record.id, older.id)
        self.assertEqual(local_result.record.id, local.id)


def _create_product(id, code, description, domain, category, default_unit="SHIPMENT"):
    return ProductCode.objects.create(
        id=id,
        code=code,
        description=description,
        domain=domain,
        category=category,
        is_gst_applicable=True,
        gst_treatment="STANDARD",
        gst_rate=Decimal("0.10"),
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=default_unit,
    )


def _product(code, description, domain, category):
    return ProductCode(code=code, description=description, domain=domain, category=category)
