from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from parties.models import Company
from pricing_v4.models import CustomerDiscount, ProductCode


class CustomerDiscountAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="discount-admin",
            password="testpass123",
            role="admin",
        )
        self.manager = User.objects.create_user(
            username="discount-manager",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(user=self.admin)

        self.customer_a = Company.objects.create(name="Customer A", is_customer=True, company_type="CUSTOMER")
        self.customer_b = Company.objects.create(name="Customer B", is_customer=True, company_type="CUSTOMER")
        self.product = ProductCode.objects.create(
            id=1005,
            code="EXP-DOC",
            description="Export Documentation",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=True,
            gst_rate=Decimal("0.1000"),
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        CustomerDiscount.objects.create(
            customer=self.customer_a,
            product_code=self.product,
            discount_type=CustomerDiscount.TYPE_PERCENTAGE,
            discount_value=Decimal("5.00"),
            currency="PGK",
        )
        CustomerDiscount.objects.create(
            customer=self.customer_b,
            product_code=self.product,
            discount_type=CustomerDiscount.TYPE_FLAT_AMOUNT,
            discount_value=Decimal("10.00"),
            currency="PGK",
        )

    def test_list_can_be_filtered_by_customer(self):
        response = self.client.get("/api/v4/discounts/", {"customer": str(self.customer_a.id)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["customer_name"], "Customer A")

    def test_bulk_upsert_creates_and_updates_customer_discount_rows(self):
        other_product = ProductCode.objects.create(
            id=1006,
            code="EXP-CLEAR",
            description="Export Clearance",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_CLEARANCE,
            is_gst_applicable=True,
            gst_rate=Decimal("0.1000"),
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        existing = CustomerDiscount.objects.get(customer=self.customer_a, product_code=self.product)

        response = self.client.post(
            "/api/v4/discounts/bulk-upsert/",
            {
                "customer": str(self.customer_a.id),
                "lines": [
                    {
                        "id": str(existing.id),
                        "product_code": self.product.id,
                        "discount_type": "FLAT_AMOUNT",
                        "discount_value": "15.00",
                        "currency": "PGK",
                        "notes": "Updated existing",
                    },
                    {
                        "product_code": other_product.id,
                        "discount_type": "PERCENTAGE",
                        "discount_value": "7.50",
                        "currency": "PGK",
                        "notes": "New row",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["saved_count"], 2)

        existing.refresh_from_db()
        self.assertEqual(existing.discount_type, CustomerDiscount.TYPE_FLAT_AMOUNT)
        self.assertEqual(existing.discount_value, Decimal("15.00"))

        created = CustomerDiscount.objects.get(customer=self.customer_a, product_code=other_product)
        self.assertEqual(created.discount_type, CustomerDiscount.TYPE_PERCENTAGE)
        self.assertEqual(created.discount_value, Decimal("7.50"))

    def test_manager_cannot_bulk_upsert_discounts(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/v4/discounts/bulk-upsert/",
            {
                "customer": str(self.customer_a.id),
                "lines": [
                    {
                        "product_code": self.product.id,
                        "discount_type": "PERCENTAGE",
                        "discount_value": "6.00",
                        "currency": "PGK",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_update_discount_rows(self):
        self.client.force_authenticate(user=self.manager)
        discount = CustomerDiscount.objects.get(customer=self.customer_a, product_code=self.product)

        response = self.client.patch(
            f"/api/v4/discounts/{discount.id}/",
            {"discount_value": "9.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_create_discount_rows(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/v4/discounts/",
            {
                "customer": str(self.customer_a.id),
                "product_code": self.product.id,
                "discount_type": "PERCENTAGE",
                "discount_value": "4.00",
                "currency": "PGK",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
