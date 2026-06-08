from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.helpers import create_location
from parties.models import Company, Contact
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal

class CommercialVisibilityTestCase(APITestCase):
    def setUp(self):
        User = get_user_model()
        
        # Create users
        self.sales_user = User.objects.create_user(
            username="sales_user",
            password="password123",
            role=User.ROLE_SALES,
        )
        self.sales_override_user = User.objects.create_user(
            username="sales_override_user",
            password="password123",
            role=User.ROLE_SALES,
            can_view_margins_override=True,
        )
        self.manager_user = User.objects.create_user(
            username="manager_user",
            password="password123",
            role=User.ROLE_MANAGER,
        )
        self.admin_user = User.objects.create_user(
            username="admin_user",
            password="password123",
            role=User.ROLE_ADMIN,
        )

    def _create_quote_for_user(self, user):
        customer = Company.objects.create(name=f"Customer for {user.username}")
        contact = Contact.objects.create(
            company=customer,
            first_name="John",
            last_name="Doe",
            email=f"john.{user.username}@example.com",
        )
        origin = create_location(name="Sydney", code="SYD")
        dest = create_location(name="Port Moresby", code="POM")
        
        quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            incoterm="DAP",
            payment_term=Quote.PaymentTerm.PREPAID,
            service_scope="D2D",
            output_currency="USD",
            origin_location=origin,
            destination_location=dest,
            status=Quote.Status.FINALIZED,
            created_by=user,
        )
        
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            status=Quote.Status.FINALIZED,
            created_by=user,
        )
        quote.latest_version = version
        quote.save()
        
        # Add a line item with cost, margin, and FX details
        QuoteLine.objects.create(
            quote_version=version,
            service_component=None,
            cost_pgk=Decimal("100.00"),
            cost_fcy=Decimal("30.00"),
            cost_fcy_currency="USD",
            sell_pgk=Decimal("150.00"),
            sell_pgk_incl_gst=Decimal("165.00"),
            sell_fcy=Decimal("45.00"),
            sell_fcy_incl_gst=Decimal("49.50"),
            sell_fcy_currency="USD",
            exchange_rate=Decimal("0.300000"),
            bucket="airfreight",
            leg="MAIN",
            cost_source="DB_TARIFF",
            is_rate_missing=False,
            product_code="FRT-TEST",
            component="FREIGHT",
            basis="Per KG",
            rule_family="PER_UNIT",
            unit_type="KG",
            rate=Decimal("3.0"),
            rate_source="DB_TARIFF",
            canonical_cost_source="DB_TARIFF",
            is_spot_sourced=False,
            is_manual_override=False,
            gst_category="service_in_PNG",
            gst_rate=Decimal("0.1000"),
            gst_amount=Decimal("15.00"),
        )
        
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=Decimal("100.00"),
            total_sell_pgk=Decimal("150.00"),
            total_sell_pgk_incl_gst=Decimal("165.00"),
            total_sell_fcy=Decimal("45.00"),
            total_sell_fcy_incl_gst=Decimal("49.50"),
            total_sell_fcy_currency="USD",
            has_missing_rates=False,
            notes="Visibility test totals",
            audit_metadata_json={
                "fx_audit": {
                    "applied": True,
                    "rate": "0.3000",
                    "base_rate": "0.3333",
                    "caf_percent": "0.1000",
                    "effective_rate_after_caf": "0.3000",
                    "direction": "SELL"
                }
            }
        )
        return quote

    def test_login_payload_includes_effective_permissions(self):
        # Test me endpoint for standard sales user
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("permissions", data)
        self.assertTrue(data["permissions"]["can_view_buy_charges"])
        self.assertFalse(data["permissions"]["can_view_margins"])

        # Test me endpoint for override sales user
        self.client.force_authenticate(user=self.sales_override_user)
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["permissions"]["can_view_buy_charges"])
        self.assertTrue(data["permissions"]["can_view_margins"])

    def test_standard_sales_user_masks_margins_and_fx_internals(self):
        quote = self._create_quote_for_user(self.sales_user)
        detail_url = reverse("quotes:quote-v3-detail", kwargs={"pk": quote.id})

        self.client.force_authenticate(user=self.sales_user)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        quote_result = data.get("quote_result")
        self.assertIsNotNone(quote_result)
        
        # Verify sell and cost are visible
        self.assertEqual(quote_result["sell_total"], "49.50")
        self.assertEqual(quote_result["total_cost_pgk"], "100.00")
        
        # Verify margins are masked as None
        self.assertIsNone(quote_result["margin_amount"])
        self.assertIsNone(quote_result["margin_percent"])
        
        # Verify FX details are masked
        fx_applied = quote_result.get("fx_applied", {})
        self.assertIsNone(fx_applied.get("base_rate"))
        self.assertIsNone(fx_applied.get("caf_percent"))
        self.assertIsNone(fx_applied.get("effective_fx_after_caf"))
        
        # Verify line items mask margins
        line_items = quote_result.get("line_items", [])
        self.assertEqual(len(line_items), 1)
        line_item = line_items[0]
        self.assertIsNone(line_item["margin_amount"])
        self.assertIsNone(line_item["margin_percent"])
        
        # Verify cost_amount in line item is visible to sales
        self.assertEqual(line_item["cost_amount"], "100.00")

    def test_sales_user_with_override_sees_margins_and_fx_details(self):
        quote = self._create_quote_for_user(self.sales_override_user)
        detail_url = reverse("quotes:quote-v3-detail", kwargs={"pk": quote.id})

        self.client.force_authenticate(user=self.sales_override_user)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        quote_result = data.get("quote_result")
        self.assertIsNotNone(quote_result)
        
        # Verify margins are visible (150 sell - 100 cost = 50 margin in PGK)
        self.assertEqual(quote_result["margin_amount"], "50.00")
        self.assertEqual(quote_result["margin_percent"], "33.33")
        
        # Verify FX details are unmasked (using 6-decimal-place and 4-decimal-place formatting)
        fx_applied = quote_result.get("fx_applied", {})
        self.assertEqual(fx_applied.get("base_rate"), "0.333300")
        self.assertEqual(fx_applied.get("caf_percent"), "0.1000")
        self.assertEqual(fx_applied.get("effective_fx_after_caf"), "0.300000")
        
        # Verify line items margins are unmasked
        line_items = quote_result.get("line_items", [])
        line_item = line_items[0]
        self.assertEqual(line_item["margin_amount"], "50.00")
        self.assertEqual(line_item["margin_percent"], "33.33")

    def test_override_does_not_grant_rate_editing(self):
        self.client.force_authenticate(user=self.sales_override_user)
        
        # 1. Try to upload a rate card (should be forbidden)
        response = self.client.post("/api/v4/rates/upload/", {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 2. Try to view/create/delete sell rates (should be forbidden)
        response = self.client.post("/api/v4/rates/import/", {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_override_does_not_grant_user_management(self):
        self.client.force_authenticate(user=self.sales_override_user)
        
        # Try to view user list (should be forbidden)
        response = self.client.get("/api/auth/users/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_user_sees_margins_and_fx_details_by_default(self):
        quote = self._create_quote_for_user(self.manager_user)
        detail_url = reverse("quotes:quote-v3-detail", kwargs={"pk": quote.id})

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        quote_result = data.get("quote_result")
        self.assertIsNotNone(quote_result)
        self.assertEqual(quote_result["margin_amount"], "50.00")
        self.assertEqual(quote_result["margin_percent"], "33.33")
