import os
import tempfile
from io import StringIO
from decimal import Decimal
from datetime import date

from django.core.management import call_command
from django.test import TestCase

from parties.models import Company
from pricing_v4.models import ProductCode, CustomerDiscount


class ImportCustomerDiscountsCommandTests(TestCase):
    def setUp(self):
        self.customer = Company.objects.create(
            name="Seed Customer",
            is_customer=True,
            company_type="CUSTOMER",
        )
        self.product = ProductCode.objects.create(
            id=1001,
            code="EXP-FRT-AIR",
            description="Export Air Freight",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal("0.1000"),
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_KG,
        )

    def _write_csv(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_import_customer_discounts_dry_run_does_not_write(self):
        csv_path = self._write_csv(
            "customer_name,product_code,discount_type,discount_value,currency,valid_from,valid_until,notes\n"
            "Seed Customer,EXP-FRT-AIR,PERCENTAGE,5.00,PGK,2026-01-01,2026-12-31,Dry run row\n"
        )

        call_command("import_customer_discounts", file=csv_path, dry_run=True, stdout=StringIO())
        self.assertEqual(CustomerDiscount.objects.count(), 0)

    def test_import_customer_discounts_create_then_update(self):
        create_csv = self._write_csv(
            "customer_name,product_code,discount_type,discount_value,currency,valid_from,valid_until,notes\n"
            "Seed Customer,EXP-FRT-AIR,PERCENTAGE,7.50,PGK,2026-01-01,2026-12-31,Initial\n"
        )
        call_command("import_customer_discounts", file=create_csv, stdout=StringIO())

        discount = CustomerDiscount.objects.get(customer=self.customer, product_code=self.product)
        self.assertEqual(discount.discount_type, CustomerDiscount.TYPE_PERCENTAGE)
        self.assertEqual(discount.discount_value, Decimal("7.50"))
        self.assertEqual(discount.valid_from, date(2026, 1, 1))
        self.assertEqual(discount.valid_until, date(2026, 12, 31))
        self.assertEqual(discount.notes, "Initial")

        update_csv = self._write_csv(
            "customer_uuid,product_code_id,discount_type,discount_value,currency,min_charge,max_charge,notes\n"
            f"{self.customer.id},{self.product.id},FLAT_AMOUNT,25.00,PGK,10.00,50.00,Updated\n"
        )
        call_command("import_customer_discounts", file=update_csv, stdout=StringIO())

        discount.refresh_from_db()
        self.assertEqual(discount.discount_type, CustomerDiscount.TYPE_FLAT_AMOUNT)
        self.assertEqual(discount.discount_value, Decimal("25.00"))
        self.assertEqual(discount.min_charge, Decimal("10.00"))
        self.assertEqual(discount.max_charge, Decimal("50.00"))
        self.assertEqual(discount.notes, "Updated")
