from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import CustomUser, Role, UserMembership
from accounts.scope import user_can_access_department
from core.models import Currency
from parties.models import Branch, Company, Department, Organization
from quotes.models import Quote, QuoteTotal, QuoteVersion
from quotes.selectors import get_quote_for_user, get_quotes_for_user, get_spes_for_user
from quotes.spot_models import SpotPricingEnvelopeDB


class QuoteAndSpotLegacyVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Company.objects.create(name="RBAC Visibility Customer", is_customer=True)
        cls.admin_user = cls._create_user("admin-user", CustomUser.ROLE_ADMIN)
        cls.finance_user = cls._create_user("finance-user", CustomUser.ROLE_FINANCE)
        cls.air_manager = cls._create_user("air-manager", CustomUser.ROLE_MANAGER, "AIR")
        cls.sea_manager = cls._create_user("sea-manager", CustomUser.ROLE_MANAGER, "SEA")
        cls.no_department_manager = cls._create_user("nodept-manager", CustomUser.ROLE_MANAGER)
        cls.air_sales = cls._create_user("air-sales", CustomUser.ROLE_SALES, "AIR")
        cls.sea_sales = cls._create_user("sea-sales", CustomUser.ROLE_SALES, "SEA")
        cls.inactive_sales = cls._create_user(
            "inactive-sales",
            CustomUser.ROLE_SALES,
            "AIR",
            is_active=False,
        )

        cls.quote_by_air_sales = cls._create_quote(cls.air_sales, "AIR-SALES", "1000.00")
        cls.quote_by_air_manager = cls._create_quote(cls.air_manager, "AIR-MANAGER", "2000.00")
        cls.quote_by_sea_sales = cls._create_quote(cls.sea_sales, "SEA-SALES", "3000.00")
        cls.quote_by_inactive_sales = cls._create_quote(
            cls.inactive_sales,
            "INACTIVE-SALES",
            "4000.00",
        )

        cls.spe_by_air_sales = cls._create_spe(cls.air_sales, "AIR_SALES")
        cls.spe_by_air_manager = cls._create_spe(cls.air_manager, "AIR_MANAGER")
        cls.spe_by_sea_sales = cls._create_spe(cls.sea_sales, "SEA_SALES")
        cls.spe_by_inactive_sales = cls._create_spe(cls.inactive_sales, "INACTIVE_SALES")

    @classmethod
    def _create_user(cls, username, role, department=None, **kwargs):
        defaults = {
            "password": "testpass123",
            "role": role,
            "department": department,
        }
        defaults.update(kwargs)
        return CustomUser.objects.create_user(username=username, **defaults)

    @classmethod
    def _create_quote(cls, user, label, total_sell_pgk):
        quote = Quote.objects.create(
            quote_number=f"RBAC-{label}",
            customer=cls.customer,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            status=Quote.Status.FINALIZED,
            created_by=user,
        )
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            status=quote.status,
            created_by=user,
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=Decimal("100.00"),
            total_sell_pgk=Decimal(total_sell_pgk),
            total_sell_pgk_incl_gst=Decimal(total_sell_pgk),
        )
        return quote

    @classmethod
    def _create_spe(cls, user, reason_code):
        return SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "PG",
                "origin_code": "POM",
                "destination_code": "LAE",
                "commodity": "GCR",
                "total_weight_kg": 10,
                "pieces": 1,
                "service_scope": "p2p",
                "payment_term": "collect",
            },
            conditions_json={},
            spot_trigger_reason_code=reason_code,
            spot_trigger_reason_text=f"Test {reason_code}",
            created_by=user,
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

    def _quote_ids_for_user(self, user):
        return set(get_quotes_for_user(user).values_list("id", flat=True))

    def _spe_ids_for_user(self, user):
        return set(get_spes_for_user(user).values_list("id", flat=True))

    def _api_quote_ids_for_user(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/v3/quotes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {row["id"] for row in response.json()["results"]}

    def test_quote_selector_admin_and_finance_see_broadly(self):
        expected_quote_ids = {
            self.quote_by_air_sales.id,
            self.quote_by_air_manager.id,
            self.quote_by_sea_sales.id,
            self.quote_by_inactive_sales.id,
        }

        self.assertSetEqual(self._quote_ids_for_user(self.admin_user), expected_quote_ids)
        self.assertSetEqual(self._quote_ids_for_user(self.finance_user), expected_quote_ids)

    def test_quote_selector_manager_sees_own_and_same_legacy_department_only(self):
        self.assertSetEqual(
            self._quote_ids_for_user(self.air_manager),
            {
                self.quote_by_air_sales.id,
                self.quote_by_air_manager.id,
                self.quote_by_inactive_sales.id,
            },
        )
        self.assertSetEqual(
            self._quote_ids_for_user(self.sea_manager),
            {self.quote_by_sea_sales.id},
        )

    def test_quote_selector_sales_sees_own_only(self):
        self.assertSetEqual(
            self._quote_ids_for_user(self.air_sales),
            {self.quote_by_air_sales.id},
        )
        self.assertSetEqual(
            self._quote_ids_for_user(self.sea_sales),
            {self.quote_by_sea_sales.id},
        )

    def test_quote_selector_anonymous_denied_and_inactive_is_legacy_compatibility(self):
        self.assertFalse(get_quotes_for_user(AnonymousUser()).exists())
        with self.assertRaises(PermissionDenied):
            get_quote_for_user(AnonymousUser(), self.quote_by_air_sales.id)

        # Legacy selector behavior: inactive users are still treated as authenticated.
        # This is intentionally documented for later cutover rather than changed here.
        self.assertSetEqual(
            self._quote_ids_for_user(self.inactive_sales),
            {self.quote_by_inactive_sales.id},
        )

    def test_quote_detail_direct_access_follows_backend_selector_rules(self):
        allowed_response = self.client.get(
            f"/api/v3/quotes/{self.quote_by_air_sales.id}/",
            HTTP_AUTHORIZATION="",
        )
        self.assertEqual(allowed_response.status_code, status.HTTP_401_UNAUTHORIZED)

        client = APIClient()
        client.force_authenticate(user=self.air_manager)

        allowed_response = client.get(f"/api/v3/quotes/{self.quote_by_air_sales.id}/")
        denied_response = client.get(f"/api/v3/quotes/{self.quote_by_sea_sales.id}/")

        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed_response.json()["id"], str(self.quote_by_air_sales.id))
        self.assertEqual(denied_response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertEqual(
            get_quote_for_user(self.air_manager, self.quote_by_air_sales.id).id,
            self.quote_by_air_sales.id,
        )
        with self.assertRaises(Http404):
            get_quote_for_user(self.air_manager, self.quote_by_sea_sales.id)

    def test_quote_list_direct_url_uses_backend_selector_not_frontend_state(self):
        quote_ids = self._api_quote_ids_for_user(self.air_sales)

        self.assertSetEqual(quote_ids, {str(self.quote_by_air_sales.id)})
        self.assertNotIn(str(self.quote_by_sea_sales.id), quote_ids)

    def test_spot_selector_admin_and_finance_see_broadly(self):
        expected_spe_ids = {
            self.spe_by_air_sales.id,
            self.spe_by_air_manager.id,
            self.spe_by_sea_sales.id,
            self.spe_by_inactive_sales.id,
        }

        self.assertSetEqual(self._spe_ids_for_user(self.admin_user), expected_spe_ids)
        self.assertSetEqual(self._spe_ids_for_user(self.finance_user), expected_spe_ids)

    def test_spot_selector_manager_same_department_and_sales_own_only(self):
        self.assertSetEqual(
            self._spe_ids_for_user(self.air_manager),
            {
                self.spe_by_air_sales.id,
                self.spe_by_air_manager.id,
                self.spe_by_inactive_sales.id,
            },
        )
        self.assertSetEqual(
            self._spe_ids_for_user(self.sea_manager),
            {self.spe_by_sea_sales.id},
        )
        self.assertSetEqual(
            self._spe_ids_for_user(self.air_sales),
            {self.spe_by_air_sales.id},
        )

    def test_spot_direct_id_access_denied_when_out_of_scope(self):
        client = APIClient()
        client.force_authenticate(user=self.air_manager)

        allowed_response = client.get(f"/api/v3/spot/envelopes/{self.spe_by_air_sales.id}/")
        denied_response = client.get(f"/api/v3/spot/envelopes/{self.spe_by_sea_sales.id}/")

        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed_response.json()["id"], str(self.spe_by_air_sales.id))
        self.assertEqual(denied_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_spot_list_direct_url_uses_backend_selector_not_frontend_state(self):
        client = APIClient()
        client.force_authenticate(user=self.air_sales)

        response = client.get("/api/v3/spot/envelopes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            {row["id"] for row in response.json()},
            {str(self.spe_by_air_sales.id)},
        )

    def test_financial_reports_inherit_quote_selector_rules_for_manager_scope(self):
        client = APIClient()
        client.force_authenticate(user=self.air_manager)

        response = client.get("/api/v3/reports/revenue_margin/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["total_revenue"], 7000.0)
        self.assertEqual(
            {row["count"] for row in data["by_mode"]},
            {3},
        )

    def test_membership_helper_scope_can_differ_from_legacy_selector_until_cutover(self):
        pgk, _ = Currency.objects.get_or_create(
            code="PGK",
            defaults={"name": "Papua New Guinean Kina"},
        )
        organization = Organization.objects.create(
            name="RBAC Helper Compare Org",
            slug="rbac-helper-compare",
            default_currency=pgk,
        )
        branch = Branch.objects.create(
            organization=organization,
            code="POM",
            name="Port Moresby",
        )
        air_department = Department.objects.create(
            organization=organization,
            branch=branch,
            code="AIR",
            name="Air Freight",
        )
        sea_department = Department.objects.create(
            organization=organization,
            branch=branch,
            code="SEA",
            name="Sea Freight",
        )
        manager_role = Role.objects.create(
            code=CustomUser.ROLE_MANAGER,
            name="Manager",
            is_system=True,
        )
        UserMembership.objects.create(
            user=self.sea_manager,
            organization=organization,
            branch=branch,
            department=air_department,
            role=manager_role,
            is_active=True,
        )

        # Current selectors still use CustomUser.department, not UserMembership.
        self.assertSetEqual(
            self._quote_ids_for_user(self.sea_manager),
            {self.quote_by_sea_sales.id},
        )
        self.assertTrue(user_can_access_department(self.sea_manager, air_department))
        self.assertFalse(user_can_access_department(self.sea_manager, sea_department))
