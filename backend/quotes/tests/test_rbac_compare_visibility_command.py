import json
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser, Role, UserMembership
from core.models import Currency
from parties.models import Branch, Company, Department, Organization
from quotes.models import Quote, QuoteTotal, QuoteVersion
from quotes.spot_models import SpotPricingEnvelopeDB


class RBACCompareVisibilityCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pgk, _ = Currency.objects.get_or_create(
            code="PGK",
            defaults={"name": "Papua New Guinean Kina"},
        )
        cls.organization = Organization.objects.create(
            name="RBAC Compare Command Org",
            slug="rbac-compare-command",
            default_currency=cls.pgk,
        )
        cls.branch = Branch.objects.create(
            organization=cls.organization,
            code="POM",
            name="Port Moresby",
        )
        cls.air_department = Department.objects.create(
            organization=cls.organization,
            branch=cls.branch,
            code="AIR",
            name="Air Freight",
        )
        cls.sea_department = Department.objects.create(
            organization=cls.organization,
            branch=cls.branch,
            code="SEA",
            name="Sea Freight",
        )
        cls.sales_role = Role.objects.create(
            code=CustomUser.ROLE_SALES,
            name="Sales",
            is_system=True,
        )
        cls.manager_role = Role.objects.create(
            code=CustomUser.ROLE_MANAGER,
            name="Manager",
            is_system=True,
        )

        cls.customer = Company.objects.create(
            name="RBAC Compare Customer",
            is_customer=True,
        )
        cls.air_manager = cls._create_user("compare-air-manager", CustomUser.ROLE_MANAGER, "AIR")
        cls.sea_manager = cls._create_user("compare-sea-manager", CustomUser.ROLE_MANAGER, "SEA")
        cls.air_sales = cls._create_user("compare-air-sales", CustomUser.ROLE_SALES, "AIR")
        cls.sea_sales = cls._create_user("compare-sea-sales", CustomUser.ROLE_SALES, "SEA")
        cls.inactive_sales = cls._create_user(
            "compare-inactive-sales",
            CustomUser.ROLE_SALES,
            "AIR",
            is_active=False,
        )

        cls.air_quote = cls._create_quote(cls.air_sales, "AIR", "1000.00")
        cls.sea_quote = cls._create_quote(cls.sea_sales, "SEA", "2000.00")
        cls.air_spe = cls._create_spe(cls.air_sales, "AIR_SPE")
        cls.sea_spe = cls._create_spe(cls.sea_sales, "SEA_SPE")

    @classmethod
    def _create_user(cls, username, role, department, **kwargs):
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
            quote_number=f"RBAC-COMPARE-{label}",
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

    def _membership_for(self, user, role, department):
        return UserMembership.objects.create(
            user=user,
            organization=self.organization,
            branch=self.branch,
            department=department,
            role=role,
            is_active=True,
        )

    def _call_command(self, *args):
        stdout = StringIO()
        call_command("rbac_compare_visibility", *args, stdout=stdout)
        return stdout.getvalue()

    def test_command_runs_successfully_with_text_output(self):
        output = self._call_command("--user", self.air_sales.username)

        self.assertIn("RBAC visibility comparison", output)
        self.assertIn(self.air_sales.username, output)
        self.assertIn("quotes:", output)
        self.assertIn("SPEs:", output)

    def test_command_runs_successfully_with_json_output(self):
        output = self._call_command("--format", "json", "--user", self.air_sales.username)

        payload = json.loads(output)
        self.assertEqual(payload["summary"]["users_compared"], 1)
        self.assertEqual(payload["users"][0]["username"], self.air_sales.username)
        self.assertIn("quotes", payload["users"][0])
        self.assertIn("spes", payload["users"][0])

    def test_command_excludes_inactive_users_by_default(self):
        output = self._call_command("--format", "json")
        payload = json.loads(output)

        usernames = {row["username"] for row in payload["users"]}
        self.assertNotIn(self.inactive_sales.username, usernames)

    def test_command_includes_inactive_users_when_requested(self):
        output = self._call_command("--format", "json", "--include-inactive")
        payload = json.loads(output)

        usernames = {row["username"] for row in payload["users"]}
        self.assertIn(self.inactive_sales.username, usernames)

    def test_command_can_filter_by_user(self):
        output = self._call_command("--format", "json", "--user", str(self.air_manager.pk))
        payload = json.loads(output)

        self.assertEqual(payload["summary"]["users_compared"], 1)
        self.assertEqual(payload["users"][0]["username"], self.air_manager.username)

    def test_command_reports_no_mismatch_when_membership_matches_legacy_department(self):
        self._membership_for(self.air_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)

        output = self._call_command("--format", "json", "--user", self.air_manager.username)
        row = json.loads(output)["users"][0]

        self.assertFalse(row["has_mismatch"])
        self.assertFalse(row["quotes"]["has_mismatch"])
        self.assertFalse(row["spes"]["has_mismatch"])

    def test_command_reports_mismatch_when_membership_differs_from_legacy_department(self):
        self._membership_for(self.sea_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)
        self._membership_for(self.sea_sales, self.sales_role, self.sea_department)

        output = self._call_command("--format", "json", "--user", self.sea_manager.username)
        row = json.loads(output)["users"][0]

        self.assertTrue(row["has_mismatch"])
        self.assertEqual(row["quotes"]["legacy_only_count"], 1)
        self.assertEqual(row["quotes"]["membership_only_count"], 1)
        self.assertEqual(row["spes"]["legacy_only_count"], 1)
        self.assertEqual(row["spes"]["membership_only_count"], 1)

    def test_show_details_includes_ids(self):
        self._membership_for(self.sea_manager, self.manager_role, self.air_department)
        self._membership_for(self.air_sales, self.sales_role, self.air_department)
        self._membership_for(self.sea_sales, self.sales_role, self.sea_department)

        output = self._call_command(
            "--format",
            "json",
            "--user",
            self.sea_manager.username,
            "--show-details",
        )
        row = json.loads(output)["users"][0]

        self.assertIn(str(self.sea_quote.id), row["quotes"]["legacy_only_ids"])
        self.assertIn(str(self.air_quote.id), row["quotes"]["membership_only_ids"])
        self.assertIn(str(self.sea_spe.id), row["spes"]["legacy_only_ids"])
        self.assertIn(str(self.air_spe.id), row["spes"]["membership_only_ids"])

    def test_default_output_does_not_include_id_lists(self):
        output = self._call_command("--format", "json", "--user", self.air_sales.username)
        row = json.loads(output)["users"][0]

        self.assertNotIn("legacy_ids", row["quotes"])
        self.assertNotIn("membership_ids", row["quotes"])
        self.assertNotIn("legacy_only_ids", row["spes"])
        self.assertNotIn(str(self.air_quote.id), output)
