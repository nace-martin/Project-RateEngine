from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from pricing_v4.models import ProductCodeCreationRequest, ProductCode


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
        self.product_code_1 = ProductCode.objects.create(
            id=1004,
            code="EXP-TERM-POM",
            description="POM Terminal Handling Fee",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit="SHIPMENT",
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
        self.assertEqual(req.normalized_source_label, "local handling fee")
        self.assertEqual(req.normalized_suggested_name, "local handling")
        
        # Test __str__
        self.assertEqual(
            str(req),
            f"Request for 'Local Handling Fee' -> 'Local Handling' (PENDING)"
        )

    def test_normalize_label_helper(self):
        self.assertEqual(
            ProductCodeCreationRequest.normalize_label("  Admin   Fee "),
            "admin fee"
        )
        self.assertEqual(
            ProductCodeCreationRequest.normalize_label("\n\t  Spaced    Out   Label \t"),
            "spaced out label"
        )
        self.assertEqual(
            ProductCodeCreationRequest.normalize_label(""),
            ""
        )
        self.assertEqual(
            ProductCodeCreationRequest.normalize_label(None),
            ""
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
        self.assertEqual(response.data["normalized_source_label"], "local handling fee")

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

    def test_role_creation_permissions(self):
        # 1. Sales can create request
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "Origin Fee",
                "suggested_name": "Origin Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
                "suggested_reason": "Sales required",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.sales_user.id)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["normalized_source_label"], "origin fee")

        # 2. Manager can create request
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "Destination Fee",
                "suggested_name": "Destination Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
                "suggested_reason": "Manager required",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.manager_user.id)

        # 3. Admin can create request
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "Admin Fee",
                "suggested_name": "Admin Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
                "suggested_reason": "Admin required",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.admin_user.id)

    def test_unauthenticated_create_blocked(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "Unauth Fee",
                "suggested_name": "Unauth Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_client_cannot_override_status_or_created_by(self):
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "Fake Fee",
                "suggested_name": "Fake Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
                "status": "APPROVED",
                "created_by": self.admin_user.id,
                "normalized_source_label": "overridden source",
                "normalized_suggested_name": "overridden name",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["created_by"], self.sales_user.id)
        # Server-side population must ignore client payload overrides
        self.assertEqual(response.data["normalized_source_label"], "fake fee")
        self.assertEqual(response.data["normalized_suggested_name"], "fake handling")

    def test_duplicate_pending_request_handling(self):
        self.client.force_authenticate(user=self.sales_user)
        
        # First creation
        response1 = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "   Duplicate    Fee   ",
                "suggested_name": "Duplicate Handling",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
            },
            format="json",
        )
        self.assertEqual(response1.status_code, 201)
        initial_id = response1.data["id"]

        # Duplicate creation with trailing space, casing difference, and multiple internal spaces
        response2 = self.client.post(
            "/api/v4/product-code-requests/",
            {
                "source_label": "duplicate fee",
                "suggested_name": "   duplicate     handling   ",
                "suggested_bucket": "HANDLING",
                "suggested_basis": "SHIPMENT",
            },
            format="json",
        )
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data["id"], initial_id)
        self.assertTrue(response2.data.get("duplicate_reused"))

        # Verify no new row was actually created in DB
        self.assertEqual(
            ProductCodeCreationRequest.objects.filter(normalized_suggested_name="duplicate handling").count(),
            1
        )

    def test_no_put_patch_delete_actions_allowed(self):
        self.client.force_authenticate(user=self.admin_user)
        
        # Update not allowed
        response = self.client.put(
            f"/api/v4/product-code-requests/{self.request_1.id}/",
            {"status": "APPROVED"},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
        
        response = self.client.patch(
            f"/api/v4/product-code-requests/{self.request_1.id}/",
            {"status": "APPROVED"},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
        
        # Delete not allowed
        response = self.client.delete(f"/api/v4/product-code-requests/{self.request_1.id}/")
        self.assertEqual(response.status_code, 405)

    def test_sales_and_manager_cannot_approve_or_reject(self):
        # Sales approve blocked
        self.client.force_authenticate(user=self.sales_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": self.product_code_1.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        # Sales reject blocked
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": "Not allowed"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        # Manager approve blocked
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": self.product_code_1.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        # Manager reject blocked
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": "Not allowed"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_approve_by_linking_product_code(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": self.product_code_1.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "APPROVED")
        self.assertEqual(response.data["approved_product_code"], self.product_code_1.id)
        self.assertEqual(response.data["approved_by"], self.admin_user.id)
        self.assertIsNotNone(response.data["approved_at"])

        # Check DB
        self.request_1.refresh_from_db()
        self.assertEqual(self.request_1.status, "APPROVED")
        self.assertEqual(self.request_1.approved_product_code, self.product_code_1)
        self.assertEqual(self.request_1.approved_by, self.admin_user)

    def test_admin_can_reject_with_reason(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": "   Replaced by existing code   "},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "REJECTED")
        self.assertEqual(response.data["rejection_reason"], "Replaced by existing code")
        self.assertEqual(response.data["approved_by"], self.admin_user.id)
        self.assertIsNotNone(response.data["rejected_at"])

        # Check DB
        self.request_1.refresh_from_db()
        self.assertEqual(self.request_1.status, "REJECTED")
        self.assertEqual(self.request_1.rejection_reason, "Replaced by existing code")

    def test_rejection_reason_validation(self):
        self.client.force_authenticate(user=self.admin_user)

        # Empty reason
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Whitespace-only reason
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": "    "},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Missing reason
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_approve_or_reject_requires_pending_status(self):
        self.client.force_authenticate(user=self.admin_user)

        # Approve it first
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": self.product_code_1.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        # Try to approve again
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": self.product_code_1.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Try to reject approved request
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/reject/",
            {"rejection_reason": "Duplicate"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_approve_with_invalid_product_code_id(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"product_code_id": 9999},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_approve_by_inline_creation_works(self):
        self.client.force_authenticate(user=self.admin_user)
        creation_data = {
            "id": 1005,
            "code": "EXP-FUEL-SUD",
            "description": "Fuel surcharge Sudan",
            "domain": "EXPORT",
            "category": "SURCHARGE",
            "is_gst_applicable": False,
            "gst_treatment": "ZERO_RATED",
            "gl_revenue_code": "4100",
            "gl_cost_code": "5100",
            "default_unit": "KG",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "APPROVED")
        self.assertEqual(response.data["approved_product_code"], 1005)
        self.assertEqual(response.data["approved_by"], self.admin_user.id)
        self.assertIsNotNone(response.data["approved_at"])

        # Verify DB ProductCode is created and linked
        pc = ProductCode.objects.get(id=1005)
        self.assertEqual(pc.code, "EXP-FUEL-SUD")
        self.assertEqual(pc.description, "Fuel surcharge Sudan")
        self.assertEqual(pc.domain, "EXPORT")
        self.assertEqual(pc.category, "SURCHARGE")
        self.assertEqual(pc.default_unit, "KG")
        self.assertEqual(pc.gl_revenue_code, "4100")
        
        self.request_1.refresh_from_db()
        self.assertEqual(self.request_1.status, "APPROVED")
        self.assertEqual(self.request_1.approved_product_code, pc)
        self.assertEqual(self.request_1.approved_by, self.admin_user)
        self.assertIsNotNone(self.request_1.approved_at)

    def test_approve_inline_creation_code_normalization(self):
        self.client.force_authenticate(user=self.admin_user)
        creation_data = {
            "id": 1006,
            "code": "  exp-fuel-norm  ",
            "description": "Fuel surcharge Normalized",
            "domain": "EXPORT",
            "category": "SURCHARGE",
            "is_gst_applicable": False,
            "gst_treatment": "ZERO_RATED",
            "gl_revenue_code": "4100",
            "gl_cost_code": "5100",
            "default_unit": "KG",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        pc = ProductCode.objects.get(id=1006)
        self.assertEqual(pc.code, "EXP-FUEL-NORM")

    def test_approve_inline_creation_invalid_id_range_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        # 1. Export domain with Domestic range ID (3xxx)
        creation_data = {
            "id": 3005,
            "code": "EXP-INVALID-RANGE",
            "description": "Invalid range",
            "domain": "EXPORT",
            "category": "SURCHARGE",
            "is_gst_applicable": False,
            "gst_treatment": "ZERO_RATED",
            "gl_revenue_code": "4100",
            "gl_cost_code": "5100",
            "default_unit": "KG",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("id", response.data.get("create_product_code_data", {}))

    def test_approve_inline_creation_duplicate_code_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        # Try to use same code as product_code_1 (EXP-TERM-POM) but in lowercase/mixedcase
        creation_data = {
            "id": 1007,
            "code": "exp-term-pom",
            "description": "Another POM Term",
            "domain": "EXPORT",
            "category": "HANDLING",
            "is_gst_applicable": True,
            "gst_treatment": "STANDARD",
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": "SHIPMENT",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.data.get("detail", ""))

    def test_approve_inline_creation_duplicate_id_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        # Try to use same ID as product_code_1 (1004)
        creation_data = {
            "id": 1004,
            "code": "EXP-DUPLICATE-ID",
            "description": "Duplicate ID desc",
            "domain": "EXPORT",
            "category": "HANDLING",
            "is_gst_applicable": True,
            "gst_treatment": "STANDARD",
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": "SHIPMENT",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_approve_both_modes_supplied_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        creation_data = {
            "id": 1008,
            "code": "EXP-BOTH-MODES",
            "description": "Both modes",
            "domain": "EXPORT",
            "category": "HANDLING",
            "is_gst_applicable": True,
            "gst_treatment": "STANDARD",
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": "SHIPMENT",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {
                "product_code_id": self.product_code_1.id,
                "create_product_code_data": creation_data
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_approve_neither_mode_supplied_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_admin_cannot_approve_create(self):
        self.client.force_authenticate(user=self.sales_user)
        creation_data = {
            "id": 1009,
            "code": "EXP-SALES-CREATE",
            "description": "Sales create",
            "domain": "EXPORT",
            "category": "HANDLING",
            "is_gst_applicable": True,
            "gst_treatment": "STANDARD",
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": "SHIPMENT",
        }
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_transaction_rollback_on_failed_creation(self):
        self.client.force_authenticate(user=self.admin_user)
        # Supplying some bad data to trigger a DB-level or serializer validation error.
        # However, serializer checks ID range. Let's make an ID validation succeed, but code length fail at the database level:
        # e.g., code length is > max_length (30). ProductCode model code has max_length=30.
        creation_data = {
            "id": 1010,
            "code": "EXP-LONG-CODE-" * 5,  # 70 chars long
            "description": "Failed creation due to long code",
            "domain": "EXPORT",
            "category": "HANDLING",
            "is_gst_applicable": True,
            "gst_treatment": "STANDARD",
            "gl_revenue_code": "4000",
            "gl_cost_code": "5000",
            "default_unit": "SHIPMENT",
        }
        
        response = self.client.post(
            f"/api/v4/product-code-requests/{self.request_1.id}/approve/",
            {"create_product_code_data": creation_data},
            format="json",
        )
        # Serializer validation might catch it (due to max_length limit from ModelSerializer), 
        # but the request status must still be PENDING:
        self.assertEqual(response.status_code, 400)
        
        self.request_1.refresh_from_db()
        self.assertEqual(self.request_1.status, "PENDING")
        self.assertIsNone(self.request_1.approved_product_code)


