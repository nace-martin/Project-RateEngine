from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role
from accounts.models import UserMembership
from parties.models import Organization, Branch, Department
from pricing_v4.models import ProductCode
from quotes.spot_models import SPEChargeLineDB, SPESourceBatchDB, SpotPricingEnvelopeDB


class DraftQuoteEndpointIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        self.other_org = Organization.objects.create(name="Other Org", slug="other-org")
        self.branch = Branch.objects.create(organization=self.org, code="POM", name="Port Moresby")
        self.other_branch = Branch.objects.create(organization=self.other_org, code="BNE", name="Brisbane")
        self.department = Department.objects.create(organization=self.org, branch=self.branch, code="AIR", name="Air Freight")
        self.other_department = Department.objects.create(
            organization=self.other_org,
            branch=self.other_branch,
            code="SEA",
            name="Sea Freight",
        )
        self.admin_user = get_user_model().objects.create_user(
            username="admin_test",
            password="testpass123",
            role=get_user_model().ROLE_ADMIN,
        )
        self.manager_user = get_user_model().objects.create_user(
            username="manager_test",
            password="testpass123",
            role=get_user_model().ROLE_MANAGER,
        )
        self.sales_user = get_user_model().objects.create_user(
            username="sales_test",
            password="testpass123",
            role=get_user_model().ROLE_SALES,
        )
        self.other_sales_user = get_user_model().objects.create_user(
            username="other_sales_test",
            password="testpass123",
            role=get_user_model().ROLE_SALES,
        )
        self.finance_user = get_user_model().objects.create_user(
            username="finance_test",
            password="testpass123",
            role=get_user_model().ROLE_FINANCE,
        )
        self._membership(self.admin_user, self.org, self.branch, self.department, "admin")
        self._membership(self.manager_user, self.org, self.branch, self.department, "manager")
        self._membership(self.sales_user, self.org, self.branch, self.department, "sales")
        self._membership(self.other_sales_user, self.other_org, self.other_branch, self.other_department, "sales")
        self._membership(self.finance_user, self.org, self.branch, self.department, "finance")
        self.spe = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "PG",
                "origin_code": "POM",
                "destination_code": "LAE",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "D2D",
            },
            conditions_json={},
            organization=self.org,
            branch=self.branch,
            department=self.department,
            owner=self.sales_user,
            created_by=self.sales_user,
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing scope rates",
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        batch = SPESourceBatchDB.objects.create(
            envelope=self.spe,
            source_kind=SPESourceBatchDB.SourceKind.AGENT,
            source_type=SPESourceBatchDB.SourceType.PDF,
            label="RBAC Batch",
        )
        product_code = ProductCode.objects.create(
            id=9122,
            code="RBAC-AIR-FREIGHT",
            description="RBAC Air Freight",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_KG,
        )
        SPEChargeLineDB.objects.create(
            envelope=self.spe,
            source_batch=batch,
            code="RBAC-AIR-FREIGHT",
            description="Air Freight",
            amount="100.00",
            currency="PGK",
            unit=SPEChargeLineDB.Unit.PER_KG,
            bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
            normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
            resolved_product_code=product_code,
            rate="1.00",
            entered_at=timezone.now(),
        )

    def _membership(self, user, organization, branch, department, role_code):
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code.title()})
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
            is_active=True,
            is_primary=True,
        )

    def test_draft_quote_read_endpoint_permissions(self):
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/"

        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.finance_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.sales_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_draft_quote_cross_scope_user_cannot_read(self):
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/"

        self.client.force_authenticate(user=self.other_sales_user)
        self.assertIn(
            self.client.get(url).status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_draft_quote_resolve_endpoint_permissions(self):
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/resolve/"

        self.assertEqual(self.client.post(url, {}, format="json").status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.finance_user)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.sales_user)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, status.HTTP_400_BAD_REQUEST)

    def test_draft_quote_cross_scope_user_cannot_resolve(self):
        url = f"/api/v3/spot/envelopes/{self.spe.id}/draft-quote/resolve/"

        self.client.force_authenticate(user=self.other_sales_user)
        self.assertIn(
            self.client.post(url, {}, format="json").status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )
