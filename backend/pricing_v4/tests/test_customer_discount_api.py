from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from parties.models import Company
from pricing_v4.models import CustomerDiscount, ProductCode


class CustomerDiscountAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="discount-manager",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(user=self.manager)

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
