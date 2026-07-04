from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, UserMembership
from crm.models import Interaction, Opportunity, Task
from parties.models import Branch, Company, Contact, Department, OperatingEntity, Organization
from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
        "DEFAULT_THROTTLE_CLASSES": [],
    }
)
class RBACBackendEnforcementAPITest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.org = Organization.objects.create(name="Express Freight Management", slug="efm")
        self.other_org = Organization.objects.create(name="Other Org", slug="other-org")
        self.oe_png = OperatingEntity.objects.create(
            organization=self.org,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        self.oe_au = OperatingEntity.objects.create(
            organization=self.org,
            code="AU",
            name="EFM Australia",
            slug="efm-au",
            country_code="AU",
        )
        self.branch_pom = Branch.objects.create(
            organization=self.org,
            operating_entity=self.oe_png,
            code="POM",
            name="Port Moresby",
        )
        self.branch_bne = Branch.objects.create(
            organization=self.org,
            operating_entity=self.oe_au,
            code="BNE",
            name="Brisbane",
        )
        self.dept_air = Department.objects.create(
            organization=self.org,
            branch=self.branch_pom,
            code="AIR",
            name="Air Freight",
        )
        self.dept_sea = Department.objects.create(
            organization=self.org,
            branch=self.branch_bne,
            code="SEA",
            name="Sea Freight",
        )
        self.sales = User.objects.create_user(username="sales", password="pass", role="sales")
        self.other_sales = User.objects.create_user(username="other-sales", password="pass", role="sales")
        self.manager = User.objects.create_user(username="manager", password="pass", role="manager")
        self.admin = User.objects.create_user(username="admin", password="pass", role="admin")
        self._membership(self.sales, self.branch_pom, self.dept_air, "sales")
        self._membership(self.other_sales, self.branch_bne, self.dept_sea, "sales")
        self._membership(self.manager, self.branch_pom, self.dept_air, "manager")
        self._membership(self.admin, self.branch_pom, self.dept_air, "admin")

        self.company = self._company("POM Customer", self.branch_pom, self.dept_air)
        self.other_company = self._company("BNE Customer", self.branch_bne, self.dept_sea)
        self.contact = self._contact(self.company, "pom@example.test", self.branch_pom, self.dept_air)
        self.other_contact = self._contact(self.other_company, "bne@example.test", self.branch_bne, self.dept_sea)
        self.quote = self._quote("QT-RBAC-001", self.company, self.sales, self.branch_pom, self.dept_air)
        self.other_quote = self._quote("QT-RBAC-002", self.other_company, self.other_sales, self.branch_bne, self.dept_sea)
        self.opportunity = self._opportunity("POM Opportunity", self.company, self.sales, self.branch_pom, self.dept_air)
        self.other_opportunity = self._opportunity("BNE Opportunity", self.other_company, self.other_sales, self.branch_bne, self.dept_sea)
        self.interaction = self._interaction(self.company, self.contact, self.opportunity, self.sales, self.branch_pom, self.dept_air)
        self.other_interaction = self._interaction(self.other_company, self.other_contact, self.other_opportunity, self.other_sales, self.branch_bne, self.dept_sea)
        self.task = self._task(self.company, self.opportunity, self.sales, self.branch_pom, self.dept_air)
        self.other_task = self._task(self.other_company, self.other_opportunity, self.other_sales, self.branch_bne, self.dept_sea)
        self.spe = self._spe(self.sales, self.branch_pom, self.dept_air, self.quote)
        self.other_spe = self._spe(self.other_sales, self.branch_bne, self.dept_sea, self.other_quote)
        self.product_request = ProductCodeCreationRequest.objects.create(
            source_label="Unknown fee",
            suggested_name="Unknown Fee",
            suggested_bucket="FREIGHT",
            suggested_basis="SHIPMENT",
            created_by=self.sales,
        )

    def _membership(self, user, branch, department, role_code):
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code.title()})
        UserMembership.objects.create(
            user=user,
            organization=self.org,
            branch=branch,
            department=department,
            role=role,
            is_active=True,
            is_primary=True,
        )

    def _company(self, name, branch, department):
        return Company.objects.create(
            name=name,
            is_customer=True,
            organization=self.org,
            branch=branch,
            department=department,
        )

    def _contact(self, company, email, branch, department):
        return Contact.objects.create(
            company=company,
            organization=self.org,
            branch=branch,
            department=department,
            first_name="Test",
            last_name="Contact",
            email=email,
        )

    def _quote(self, number, company, owner, branch, department):
        return Quote.objects.create(
            customer=company,
            organization=self.org,
            branch=branch,
            department=department,
            owner=owner,
            created_by=owner,
            quote_number=number,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            output_currency="PGK",
            status=Quote.Status.DRAFT,
        )

    def _opportunity(self, title, company, owner, branch, department):
        return Opportunity.objects.create(
            company=company,
            title=title,
            service_type="AIR",
            owner=owner,
            organization=self.org,
            branch=branch,
            department=department,
        )

    def _interaction(self, company, contact, opportunity, author, branch, department):
        return Interaction.objects.create(
            company=company,
            contact=contact,
            opportunity=opportunity,
            author=author,
            organization=self.org,
            branch=branch,
            department=department,
            interaction_type=Interaction.InteractionType.CALL,
            summary="Call",
        )

    def _task(self, company, opportunity, owner, branch, department):
        return Task.objects.create(
            company=company,
            opportunity=opportunity,
            owner=owner,
            organization=self.org,
            branch=branch,
            department=department,
            description="Follow up",
            due_date=timezone.now().date(),
        )

    def _spe(self, user, branch, department, quote):
        return SpotPricingEnvelopeDB.objects.create(
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "PG",
                "origin_code": "POM",
                "destination_code": "LAE",
                "commodity": "GCR",
                "total_weight_kg": 1,
                "pieces": 1,
                "service_scope": "p2p",
            },
            conditions_json={},
            organization=self.org,
            branch=branch,
            department=department,
            owner=user,
            created_by=user,
            quote=quote,
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def _ids(self, response):
        data = response.data.get("results", response.data) if hasattr(response.data, "get") else response.data
        return {str(item["id"]) for item in data}

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def assert_hidden_from_sales(self, list_name, detail_name, own_obj, other_obj):
        self._login(self.sales)
        list_response = self.client.get(reverse(list_name))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(str(own_obj.id), self._ids(list_response))
        self.assertNotIn(str(other_obj.id), self._ids(list_response))
        detail_response = self.client.get(reverse(detail_name, kwargs={"pk": other_obj.pk}))
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_company_list_retrieve_cross_scope(self):
        self.assert_hidden_from_sales("parties:customer-v3-list", "parties:customer-v3-detail", self.company, self.other_company)

    def test_contact_list_cross_scope_and_no_retrieve_claim(self):
        self._login(self.sales)
        response = self.client.get(reverse("parties:company-contacts-v3", kwargs={"company_id": self.other_company.id}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        with self.assertRaises(NoReverseMatch):
            reverse("parties:contact-detail", kwargs={"pk": self.other_contact.pk})

    def test_opportunity_list_retrieve_cross_scope(self):
        self.assert_hidden_from_sales("crm:opportunity-list", "crm:opportunity-detail", self.opportunity, self.other_opportunity)

    def test_interaction_list_retrieve_cross_scope(self):
        self.assert_hidden_from_sales("crm:interaction-list", "crm:interaction-detail", self.interaction, self.other_interaction)

    def test_task_list_retrieve_cross_scope(self):
        self.assert_hidden_from_sales("crm:task-list", "crm:task-detail", self.task, self.other_task)

    def test_quote_list_retrieve_cross_scope(self):
        self.assert_hidden_from_sales("quotes:quote-v3-list", "quotes:quote-v3-detail", self.quote, self.other_quote)

    def test_spot_envelope_read_write_cross_scope(self):
        self._login(self.sales)
        list_response = self.client.get(reverse("quotes:spot-envelope-list-create"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(str(self.spe.id), self._ids(list_response))
        self.assertNotIn(str(self.other_spe.id), self._ids(list_response))
        detail_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": self.other_spe.id})
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(detail_url, {"conditions": {}}, format="json").status_code, status.HTTP_404_NOT_FOUND)

    def test_draft_quote_read_resolve_cross_scope(self):
        self._login(self.sales)
        read_url = reverse("quotes:spot-envelope-draft-quote", kwargs={"envelope_id": self.other_spe.id})
        resolve_url = reverse("quotes:spot-envelope-draft-quote-resolve", kwargs={"envelope_id": self.other_spe.id})
        self.assertEqual(self.client.get(read_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(resolve_url, {}, format="json").status_code, status.HTTP_404_NOT_FOUND)

    def test_product_code_request_review_role_scope(self):
        create_url = reverse("product-code-requests-list")
        detail_url = reverse("product-code-requests-detail", kwargs={"pk": self.product_request.pk})
        approve_url = reverse("product-code-requests-approve", kwargs={"pk": self.product_request.pk})
        self._login(self.sales)
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(
                create_url,
                {
                    "source_label": "Terminal fee",
                    "suggested_name": "Terminal Fee",
                    "suggested_bucket": "HANDLING",
                    "suggested_basis": "SHIPMENT",
                },
                format="json",
            ).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            self.client.post(
                create_url,
                {
                    "source_label": "Other branch fee",
                    "suggested_name": "Other Branch Fee",
                    "suggested_bucket": "HANDLING",
                    "suggested_basis": "SHIPMENT",
                    "source_envelope": str(self.other_spe.id),
                },
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(self.client.post(approve_url, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        product = ProductCode.objects.create(
            id=987654,
            code="RBAC-PC",
            description="RBAC Product",
            domain="AIR",
            category=ProductCode.CATEGORY_HANDLING,
            default_unit=ProductCode.UNIT_SHIPMENT,
            is_gst_applicable=False,
        )
        self._login(self.admin)
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(approve_url, {"product_code_id": product.id}, format="json").status_code, status.HTTP_200_OK)

    def test_anonymous_blocked(self):
        self.client.force_authenticate(user=None)
        for url in [
            reverse("parties:customer-v3-list"),
            reverse("crm:opportunity-list"),
            reverse("quotes:quote-v3-list"),
            reverse("quotes:spot-envelope-list-create"),
        ]:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_manager_override_same_scope(self):
        self._login(self.manager)
        response = self.client.get(reverse("quotes:quote-v3-detail", kwargs={"pk": self.quote.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_override(self):
        self._login(self.admin)
        response = self.client.get(reverse("quotes:quote-v3-detail", kwargs={"pk": self.other_quote.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cross_operating_entity_branch_department_blocked(self):
        self._login(self.sales)
        for endpoint, obj in [
            ("parties:customer-v3-detail", self.other_company),
            ("crm:opportunity-detail", self.other_opportunity),
            ("quotes:quote-v3-detail", self.other_quote),
            ("quotes:spot-envelope-detail", self.other_spe),
        ]:
            kwargs = {"envelope_id": obj.pk} if endpoint == "quotes:spot-envelope-detail" else {"pk": obj.pk}
            self.assertEqual(self.client.get(reverse(endpoint, kwargs=kwargs)).status_code, status.HTTP_404_NOT_FOUND)

    def test_id_guessing_blocked(self):
        self._login(self.sales)
        guessed_urls = [
            reverse("parties:customer-v3-detail", kwargs={"pk": self.other_company.pk}),
            reverse("crm:opportunity-detail", kwargs={"pk": self.other_opportunity.pk}),
            reverse("crm:interaction-detail", kwargs={"pk": self.other_interaction.pk}),
            reverse("crm:task-detail", kwargs={"pk": self.other_task.pk}),
            reverse("quotes:quote-v3-detail", kwargs={"pk": self.other_quote.pk}),
            reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": self.other_spe.pk}),
            reverse("quotes:spot-envelope-draft-quote", kwargs={"envelope_id": self.other_spe.pk}),
        ]
        for url in guessed_urls:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
