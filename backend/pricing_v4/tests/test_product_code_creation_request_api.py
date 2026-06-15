from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from pricing_v4.models import ProductCodeCreationRequest


class ProductCodeCreationRequestTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="admin-user",
            password="testpass123",
            role="admin",
        )
        self.manager_user = User.objects.create_user(
            username="manager-user",
            password="testpass123",
            role="manager",
        )
        self.sales_user = User.objects.create_user(
            username="sales-user",
            password="testpass123",
            role="sales",
        )

        # Create some test requests
        self.request_1 = ProductCodeCreationRequest.objects.create(
            source_label="Local Handling Fee",
            suggested_name="Local Handling",
            suggested_bucket="HANDLING",
            suggested_basis="SHIPMENT",
            suggested_reason="Needed for air freight imports",
            created_by=self.sales_user,
        )
        self.request_2 = ProductCodeCreationRequest.objects.create(
            source_label="Export Fuel Surcharge",
            suggested_name="Fuel Surcharge",
            suggested_bucket="SURCHARGE",
            suggested_basis="KG",
            suggested_reason="Required for rising fuel costs",
            created_by=self.manager_user,
        )

    def test_model_fields_and_string_representation(self):
        req = self.request_1
        self.assertEqual(req.status, ProductCodeCreationRequest.STATUS_PENDING)
        self.assertIsNone(req.approved_by)
        self.assertIsNone(req.approved_at)
        self.assertIsNone(req.rejected_at)
        self.assertIsNone(req.rejection_reason)
        self.assertIsNotNone(req.created_at)
        self.assertIsNotNone(req.updated_at)
        
        # Test __str__
        self.assertEqual(
            str(req),
            f"Request for 'Local Handling Fee' -> 'Local Handling' (PENDING)"
        )

    def test_admin_can_list_and_retrieve_requests(self):
        self.client.force_authenticate(user=self.admin_user)
        
        # List
        response = self.client.get("/api/v4/product-code-requests/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        # Check ordering (newest first)
        self.assertEqual(response.data[0]["id"], self.request_2.id)
        self.assertEqual(response.data[1]["id"], self.request_1.id)
        
        # Retrieve
        response = self.client.get(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source_label"], "Local Handling Fee")
        self.assertEqual(response.data["created_by_username"], "sales-user")

    def test_manager_forbidden_to_list_or_retrieve(self):
        self.client.force_authenticate(user=self.manager_user)
        
        response = self.client.get("/api/v4/product-code-requests/")
        self.assertEqual(response.status_code, 403)
        
        response = self.client.get(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 403)

    def test_sales_forbidden_to_list_or_retrieve(self):
        self.client.force_authenticate(user=self.sales_user)
        
        response = self.client.get("/api/v4/product-code-requests/")
        self.assertEqual(response.status_code, 403)
        
        response = self.client.get(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_blocked(self):
        response = self.client.get("/api/v4/product-code-requests/")
        self.assertEqual(response.status_code, 401)
        
        response = self.client.get(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 401)

    def test_no_write_actions_allowed(self):
        self.client.force_authenticate(user=self.admin_user)
        
        # Create not allowed
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "New Inbound Fee",
                "suggested_name": "Inbound Fee",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
        
        # Update not allowed
        response = self.client.put(
            f"/api/v4/product-code-requests/{self.request_1.id}/",
            {"status": "APPROVED"},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
        
        # Delete not allowed
        response = self.client.delete(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 405)
