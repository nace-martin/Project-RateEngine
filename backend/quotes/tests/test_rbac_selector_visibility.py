from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import CustomUser, Role, UserMembership
from accounts.scope import get_active_memberships, user_can_access_department
from core.models import Currency
from parties.models import Branch, Company, Department, Organization
from quotes.models import Quote, QuoteTotal, QuoteVersion
from quotes.selectors import get_quote_for_user, get_quotes_for_user, get_spes_for_user
from quotes.spot_models import SpotPricingEnvelopeDB
from quotes.rbac_selector_comparison import (
    compare_quote_visibility,
    compare_spe_visibility,
)


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
        manager_role, _ = Role.objects.get_or_create(
            code=CustomUser.ROLE_MANAGER,
            organization=None,
            defaults={
                "name": "Manager",
                "is_system": True,
            },
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


class QuoteAndSpotScopeComparisonTests(QuoteAndSpotLegacyVisibilityTests):
    def setUp(self):
        self.pgk, _ = Currency.objects.get_or_create(
            code="PGK",
            defaults={"name": "Papua New Guinean Kina"},
        )
        self.organization = Organization.objects.create(
            name="RBAC Selector Compare Org",
            slug="rbac-selector-compare",
            default_currency=self.pgk,
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            code="POM",
            name="Port Moresby",
        )
        self.air_department = Department.objects.create(
            organization=self.organization,
            branch=self.branch,
            code="AIR",
            name="Air Freight",
        )
        self.sea_department = Department.objects.create(
            organization=self.organization,
            branch=self.branch,
            code="SEA",
            name="Sea Freight",
        )
        self.sales_role = Role.objects.create(
            code=CustomUser.ROLE_SALES,
            name="Sales",
            is_system=True,
        )
        self.manager_role = Role.objects.create(
            code=CustomUser.ROLE_MANAGER,
            name="Manager",
            is_system=True,
        )
        self.admin_role = Role.objects.create(
            code=CustomUser.ROLE_ADMIN,
            name="Admin",
            is_system=True,
        )
        self.finance_role = Role.objects.create(
            code=CustomUser.ROLE_FINANCE,
            name="Finance",
            is_system=True,
        )

    def _membership_for(self, user, role, department, *, active=True):
        return UserMembership.objects.create(
            user=user,
            organization=self.organization,
            branch=self.branch,
            department=department,
            role=role,
            is_active=active,
        )

    def _assert_no_quote_or_spe_mismatch(self, user):
        quote_comparison = compare_quote_visibility(user)
        spe_comparison = compare_spe_visibility(user)

        self.assertFalse(quote_comparison.has_mismatch)
        self.assertFalse(spe_comparison.has_mismatch)
        self.assertSetEqual(quote_comparison.legacy_ids, quote_comparison.scope_ids)
        self.assertSetEqual(spe_comparison.legacy_ids, spe_comparison.scope_ids)

    def test_no_active_memberships_fall_back_to_legacy_behavior(self):
        self.assertEqual(list(get_active_memberships(self.air_manager)), [])

        self._assert_no_quote_or_spe_mismatch(self.air_manager)

    def test_active_membership_matching_legacy_department_has_no_mismatch(self):
        self._membership_for(self.air_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)
        self._membership_for(self.inactive_sales, self.sales_role, self.air_department)
        self._membership_for(self.sea_sales, self.sales_role, self.sea_department)

        self._assert_no_quote_or_spe_mismatch(self.air_manager)

    def test_active_membership_different_from_legacy_department_reports_mismatch(self):
        self._membership_for(self.sea_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)
        self._membership_for(self.air_manager, self.manager_role, self.air_department)
        self._membership_for(self.sea_sales, self.sales_role, self.sea_department)

        quote_comparison = compare_quote_visibility(self.sea_manager)
        spe_comparison = compare_spe_visibility(self.sea_manager)

        self.assertTrue(quote_comparison.has_mismatch)
        self.assertSetEqual(quote_comparison.legacy_ids, {self.quote_by_sea_sales.id})
        self.assertSetEqual(
            quote_comparison.scope_ids,
            {self.quote_by_air_sales.id, self.quote_by_air_manager.id},
        )
        self.assertSetEqual(quote_comparison.only_legacy_ids, {self.quote_by_sea_sales.id})
        self.assertSetEqual(
            quote_comparison.only_scope_ids,
            {self.quote_by_air_sales.id, self.quote_by_air_manager.id},
        )

        self.assertTrue(spe_comparison.has_mismatch)
        self.assertSetEqual(spe_comparison.legacy_ids, {self.spe_by_sea_sales.id})
        self.assertSetEqual(
            spe_comparison.scope_ids,
            {self.spe_by_air_sales.id, self.spe_by_air_manager.id},
        )

    def test_admin_and_finance_organization_wide_comparison_has_no_mismatch(self):
        self._membership_for(self.admin_user, self.admin_role, None)
        self._membership_for(self.finance_user, self.finance_role, None)

        self._assert_no_quote_or_spe_mismatch(self.admin_user)
        self._assert_no_quote_or_spe_mismatch(self.finance_user)

    def test_sales_own_only_comparison_has_no_mismatch(self):
        self._membership_for(self.air_sales, self.sales_role, self.air_department)

        self._assert_no_quote_or_spe_mismatch(self.air_sales)

    def test_manager_same_department_legacy_comparison_has_no_mismatch(self):
        self._membership_for(self.air_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)
        self._membership_for(self.inactive_sales, self.sales_role, self.air_department)

        self._assert_no_quote_or_spe_mismatch(self.air_manager)

    def test_anonymous_and_inactive_comparison_documents_current_difference(self):
        anonymous_quote_comparison = compare_quote_visibility(AnonymousUser())
        anonymous_spe_comparison = compare_spe_visibility(AnonymousUser())

        self.assertFalse(anonymous_quote_comparison.has_mismatch)
        self.assertFalse(anonymous_spe_comparison.has_mismatch)
        self.assertSetEqual(anonymous_quote_comparison.legacy_ids, frozenset())
        self.assertSetEqual(anonymous_spe_comparison.legacy_ids, frozenset())

        self._membership_for(self.inactive_sales, self.sales_role, self.air_department)
        inactive_quote_comparison = compare_quote_visibility(self.inactive_sales)
        inactive_spe_comparison = compare_spe_visibility(self.inactive_sales)

        self.assertTrue(inactive_quote_comparison.has_mismatch)
        self.assertSetEqual(
            inactive_quote_comparison.legacy_ids,
            {self.quote_by_inactive_sales.id},
        )
        self.assertSetEqual(inactive_quote_comparison.scope_ids, frozenset())
        self.assertSetEqual(
            inactive_spe_comparison.legacy_ids,
            {self.spe_by_inactive_sales.id},
        )
        self.assertSetEqual(inactive_spe_comparison.scope_ids, frozenset())
