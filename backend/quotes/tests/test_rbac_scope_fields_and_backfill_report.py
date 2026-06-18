import json
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser, Role, UserMembership
from core.models import Currency
from parties.models import Branch, Company, Department, Organization
from quotes.management.commands.rbac_scope_backfill_report import (
    STATUS_ALREADY_SCOPED,
    STATUS_AMBIGUOUS,
    STATUS_SINGLE_MEMBERSHIP,
    STATUS_UNKNOWN,
)
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


class RBACScopeFieldsAndBackfillReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pgk, _ = Currency.objects.get_or_create(
            code="PGK",
            defaults={"name": "Papua New Guinean Kina"},
        )
        cls.organization = Organization.objects.create(
            name="RBAC Scope Field Org",
            slug="rbac-scope-field-org",
            default_currency=cls.pgk,
        )
        cls.branch = Branch.objects.create(
            organization=cls.organization,
            code="POM",
            name="Port Moresby",
        )
        cls.other_branch = Branch.objects.create(
            organization=cls.organization,
            code="LAE",
            name="Lae",
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
        cls.other_branch_department = Department.objects.create(
            organization=cls.organization,
            branch=cls.other_branch,
            code="LAND",
            name="Road Freight",
        )
        cls.explicit_organization = Organization.objects.create(
            name="Explicit Scope Org",
            slug="explicit-scope-org",
            default_currency=cls.pgk,
        )
        cls.explicit_branch = Branch.objects.create(
            organization=cls.explicit_organization,
            code="MTK",
            name="Mount Hagen",
        )
        cls.explicit_department = Department.objects.create(
            organization=cls.explicit_organization,
            branch=cls.explicit_branch,
            code="FIN",
            name="Finance",
        )
        cls.manager_role = Role.objects.create(
            code=CustomUser.ROLE_MANAGER,
            name="Manager",
            is_system=True,
        )
        cls.customer = Company.objects.create(
            name="RBAC Scope Customer",
            is_customer=True,
        )

    def _create_user(self, username, **kwargs):
        defaults = {
            "password": "testpass123",
            "role": CustomUser.ROLE_SALES,
        }
        defaults.update(kwargs)
        return CustomUser.objects.create_user(username=username, **defaults)

    def _create_quote(self, user=None, **kwargs):
        defaults = {
            "customer": self.customer,
            "mode": "AIR",
            "shipment_type": Quote.ShipmentType.IMPORT,
            "status": Quote.Status.DRAFT,
            "created_by": user,
        }
        defaults.update(kwargs)
        return Quote.objects.create(**defaults)

    def _create_spe(self, user=None, **kwargs):
        defaults = {
            "status": SpotPricingEnvelopeDB.Status.DRAFT,
            "shipment_context_json": {
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
            "conditions_json": {},
            "spot_trigger_reason_code": "TEST",
            "spot_trigger_reason_text": "Test SPE",
            "created_by": user,
            "expires_at": timezone.now() + timezone.timedelta(hours=24),
        }
        defaults.update(kwargs)
        return SpotPricingEnvelopeDB.objects.create(**defaults)

    def _create_legacy_unscoped_quote(self, user=None, **kwargs):
        defaults = {
            "id": uuid.uuid4(),
            "quote_number": f"LEGACY-{uuid.uuid4().hex[:8].upper()}",
            "customer": self.customer,
            "mode": "AIR",
            "shipment_type": Quote.ShipmentType.IMPORT,
            "status": Quote.Status.DRAFT,
            "created_by": user,
        }
        defaults.update(kwargs)
        quote = Quote(**defaults)
        Quote.objects.bulk_create([quote])
        return quote

    def _create_legacy_unscoped_spe(self, user=None, **kwargs):
        defaults = {
            "id": uuid.uuid4(),
            "status": SpotPricingEnvelopeDB.Status.DRAFT,
            "shipment_context_json": {
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
            "shipment_context_hash": f"legacy-{uuid.uuid4().hex}",
            "conditions_json": {},
            "spot_trigger_reason_code": "TEST",
            "spot_trigger_reason_text": "Test SPE",
            "created_by": user,
            "expires_at": timezone.now() + timezone.timedelta(hours=24),
        }
        defaults.update(kwargs)
        spe = SpotPricingEnvelopeDB(**defaults)
        SpotPricingEnvelopeDB.objects.bulk_create([spe])
        return spe

    def _membership_for(self, user, department, *, branch=None, is_primary=True):
        return UserMembership.objects.create(
            user=user,
            organization=self.organization,
            branch=branch or self.branch,
            department=department,
            role=self.manager_role,
            is_primary=is_primary,
            is_active=True,
        )

    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_scope_backfill_report", *args, stdout=stdout)
        return stdout.getvalue()

    def _call_backfill(self, *args):
        stdout = StringIO()
        call_command("rbac_scope_backfill", *args, stdout=stdout)
        return stdout.getvalue()

    def test_quote_scope_fields_exist_and_are_nullable(self):
        for field_name in ("branch", "department", "owner"):
            field = Quote._meta.get_field(field_name)
            self.assertTrue(field.null)
            self.assertTrue(field.blank)

    def test_spot_scope_fields_exist_and_are_nullable(self):
        for field_name in ("organization", "branch", "department", "owner"):
            field = SpotPricingEnvelopeDB._meta.get_field(field_name)
            self.assertTrue(field.null)
            self.assertTrue(field.blank)

    def test_creating_quote_without_scope_fields_still_works(self):
        quote = self._create_quote()

        self.assertIsNone(quote.branch_id)
        self.assertIsNone(quote.department_id)
        self.assertIsNone(quote.owner_id)

    def test_creating_spot_without_scope_fields_still_works(self):
        spe = self._create_spe()

        self.assertIsNone(spe.organization_id)
        self.assertIsNone(spe.branch_id)
        self.assertIsNone(spe.department_id)
        self.assertIsNone(spe.owner_id)

    def test_quote_single_membership_populates_scope(self):
        user = self._create_user("quote-single-membership-user")
        self._membership_for(user, self.air_department)

        quote = self._create_quote(user)

        self.assertEqual(quote.organization_id, self.organization.id)
        self.assertEqual(quote.branch_id, self.branch.id)
        self.assertEqual(quote.department_id, self.air_department.id)
        self.assertEqual(quote.owner_id, user.id)

    def test_quote_legacy_organization_only_populates_organization_and_owner(self):
        user = self._create_user("quote-legacy-org-user", organization=self.organization)

        quote = self._create_quote(user)

        self.assertEqual(quote.organization_id, self.organization.id)
        self.assertEqual(quote.owner_id, user.id)
        self.assertIsNone(quote.branch_id)
        self.assertIsNone(quote.department_id)

    def test_quote_multiple_memberships_do_not_guess_branch_or_department(self):
        user = self._create_user("quote-multi-membership-user")
        self._membership_for(user, self.air_department)
        self._membership_for(
            user,
            self.other_branch_department,
            branch=self.other_branch,
            is_primary=False,
        )

        quote = self._create_quote(user)

        self.assertEqual(quote.organization_id, self.organization.id)
        self.assertEqual(quote.owner_id, user.id)
        self.assertIsNone(quote.branch_id)
        self.assertIsNone(quote.department_id)

    def test_explicit_quote_scope_values_are_not_overridden(self):
        user = self._create_user("quote-explicit-scope-user")
        explicit_owner = self._create_user("quote-explicit-owner")
        self._membership_for(user, self.air_department)

        quote = self._create_quote(
            user,
            organization=self.explicit_organization,
            branch=self.explicit_branch,
            department=self.explicit_department,
            owner=explicit_owner,
        )

        self.assertEqual(quote.organization_id, self.explicit_organization.id)
        self.assertEqual(quote.branch_id, self.explicit_branch.id)
        self.assertEqual(quote.department_id, self.explicit_department.id)
        self.assertEqual(quote.owner_id, explicit_owner.id)

    def test_spot_single_membership_populates_scope(self):
        user = self._create_user("spot-single-membership-user")
        self._membership_for(user, self.air_department)

        spe = self._create_spe(user)

        self.assertEqual(spe.organization_id, self.organization.id)
        self.assertEqual(spe.branch_id, self.branch.id)
        self.assertEqual(spe.department_id, self.air_department.id)
        self.assertEqual(spe.owner_id, user.id)

    def test_spot_legacy_organization_only_populates_organization_and_owner(self):
        user = self._create_user("spot-legacy-org-user", organization=self.organization)

        spe = self._create_spe(user)

        self.assertEqual(spe.organization_id, self.organization.id)
        self.assertEqual(spe.owner_id, user.id)
        self.assertIsNone(spe.branch_id)
        self.assertIsNone(spe.department_id)

    def test_spot_multiple_memberships_do_not_guess_branch_or_department(self):
        user = self._create_user("spot-multi-membership-user")
        self._membership_for(user, self.air_department)
        self._membership_for(
            user,
            self.other_branch_department,
            branch=self.other_branch,
            is_primary=False,
        )

        spe = self._create_spe(user)

        self.assertEqual(spe.organization_id, self.organization.id)
        self.assertEqual(spe.owner_id, user.id)
        self.assertIsNone(spe.branch_id)
        self.assertIsNone(spe.department_id)

    def test_dry_run_report_command_runs_for_quotes(self):
        self._create_quote()

        output = self._call_report("--model", "quote")

        self.assertIn("RBAC scope backfill dry-run report", output)
        self.assertIn("quote:", output)

    def test_dry_run_report_command_runs_for_spot(self):
        self._create_spe()

        output = self._call_report("--model", "spot")

        self.assertIn("RBAC scope backfill dry-run report", output)
        self.assertIn("spot:", output)

    def test_single_membership_candidate_is_reported(self):
        user = self._create_user("single-membership-user")
        self._membership_for(user, self.air_department)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_report("--format", "json", "--model", "quote", "--show-details")
        payload = json.loads(output)
        detail = self._detail_for(payload, "quote", quote.id)

        self.assertEqual(detail["status"], STATUS_SINGLE_MEMBERSHIP)
        self.assertEqual(detail["candidate"]["department_code"], "AIR")
        self.assertEqual(detail["candidate"]["branch_code"], "POM")

    def test_existing_quote_organization_is_reported_as_already_scoped(self):
        quote = self._create_quote(organization=self.organization)

        output = self._call_report("--format", "json", "--model", "quote", "--show-details")
        payload = json.loads(output)
        detail = self._detail_for(payload, "quote", quote.id)

        self.assertEqual(detail["status"], STATUS_ALREADY_SCOPED)
        self.assertEqual(detail["current_scope"]["organization_id"], str(self.organization.id))

    def test_multiple_memberships_are_marked_ambiguous(self):
        user = self._create_user("ambiguous-membership-user")
        self._membership_for(user, self.air_department)
        self._membership_for(user, self.sea_department, is_primary=False)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_report("--format", "json", "--model", "quote", "--show-details")
        payload = json.loads(output)
        detail = self._detail_for(payload, "quote", quote.id)

        self.assertEqual(detail["status"], STATUS_AMBIGUOUS)
        self.assertEqual(detail["membership_count"], 2)
        self.assertEqual(len(detail["candidates"]), 2)

    def test_missing_membership_is_marked_unknown(self):
        quote = self._create_quote()
        spe = self._create_spe()

        output = self._call_report("--format", "json", "--show-details")
        payload = json.loads(output)

        self.assertEqual(self._detail_for(payload, "quote", quote.id)["status"], STATUS_UNKNOWN)
        self.assertEqual(self._detail_for(payload, "spot", spe.id)["status"], STATUS_UNKNOWN)

    def test_command_does_not_write_by_default(self):
        user = self._create_user("dry-run-user")
        self._membership_for(user, self.air_department)
        quote = self._create_legacy_unscoped_quote(user)
        spe = self._create_legacy_unscoped_spe(user)

        self._call_report("--format", "json", "--show-details")

        quote.refresh_from_db()
        spe.refresh_from_db()
        self.assertIsNone(quote.branch_id)
        self.assertIsNone(quote.department_id)
        self.assertIsNone(quote.owner_id)
        self.assertIsNone(spe.organization_id)
        self.assertIsNone(spe.branch_id)
        self.assertIsNone(spe.department_id)
        self.assertIsNone(spe.owner_id)

    def test_backfill_dry_run_writes_nothing(self):
        user = self._create_user("backfill-dry-run-user")
        self._membership_for(user, self.air_department)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_backfill("--model", "quote", "--format", "json", "--show-details")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(payload["summary"]["safe_candidates"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertIsNone(quote.branch_id)
        self.assertIsNone(quote.department_id)
        self.assertIsNone(quote.owner_id)

    def test_backfill_write_updates_safe_single_membership_quote(self):
        user = self._create_user("backfill-quote-user")
        self._membership_for(user, self.air_department)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_backfill("--write", "--model", "quote", "--format", "json", "--show-details")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertTrue(payload["write_enabled"])
        self.assertEqual(payload["summary"]["safe_candidates"], 1)
        self.assertEqual(payload["summary"]["updated"], 1)
        self.assertEqual(quote.organization_id, self.organization.id)
        self.assertEqual(quote.branch_id, self.branch.id)
        self.assertEqual(quote.department_id, self.air_department.id)
        self.assertEqual(quote.owner_id, user.id)

    def test_backfill_write_updates_safe_single_membership_spot(self):
        user = self._create_user("backfill-spot-user")
        self._membership_for(user, self.air_department)
        spe = self._create_legacy_unscoped_spe(user)

        output = self._call_backfill("--write", "--model", "spot", "--format", "json", "--show-details")

        spe.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["safe_candidates"], 1)
        self.assertEqual(payload["summary"]["updated"], 1)
        self.assertEqual(spe.organization_id, self.organization.id)
        self.assertEqual(spe.branch_id, self.branch.id)
        self.assertEqual(spe.department_id, self.air_department.id)
        self.assertEqual(spe.owner_id, user.id)

    def test_backfill_skips_ambiguous_membership(self):
        user = self._create_user("backfill-ambiguous-user")
        self._membership_for(user, self.air_department)
        self._membership_for(user, self.other_branch_department, branch=self.other_branch, is_primary=False)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_backfill("--write", "--model", "quote", "--format", "json")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["skipped_ambiguous"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertIsNone(quote.branch_id)

    def test_backfill_skips_no_membership(self):
        user = self._create_user("backfill-no-membership-user")
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_backfill("--write", "--model", "quote", "--format", "json")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["skipped_no_membership"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertIsNone(quote.owner_id)

    def test_backfill_skips_no_created_by(self):
        quote = self._create_legacy_unscoped_quote()

        output = self._call_backfill("--write", "--model", "quote", "--format", "json")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["skipped_no_created_by"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertIsNone(quote.owner_id)

    def test_backfill_skips_inactive_user(self):
        user = self._create_user("backfill-inactive-user", is_active=False)
        quote = self._create_legacy_unscoped_quote(user)

        output = self._call_backfill("--write", "--model", "quote", "--format", "json")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["skipped_inactive_user"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertIsNone(quote.owner_id)

    def test_backfill_does_not_overwrite_existing_explicit_scope_values(self):
        user = self._create_user("backfill-explicit-user")
        self._membership_for(user, self.air_department)
        explicit_owner = self._create_user("backfill-explicit-owner")
        quote = self._create_legacy_unscoped_quote(
            user,
            organization=self.explicit_organization,
            branch=self.explicit_branch,
            department=self.explicit_department,
            owner=explicit_owner,
        )

        output = self._call_backfill("--write", "--model", "quote", "--format", "json")

        quote.refresh_from_db()
        payload = json.loads(output)
        self.assertEqual(payload["summary"]["already_scoped_noop"], 1)
        self.assertEqual(payload["summary"]["updated"], 0)
        self.assertEqual(quote.organization_id, self.explicit_organization.id)
        self.assertEqual(quote.branch_id, self.explicit_branch.id)
        self.assertEqual(quote.department_id, self.explicit_department.id)
        self.assertEqual(quote.owner_id, explicit_owner.id)

    def _detail_for(self, payload, model_name, record_id):
        record_id = str(record_id)
        for detail in payload["models"][model_name]["details"]:
            if detail["id"] == record_id:
                return detail
        self.fail(f"Missing {model_name} detail for {record_id}")
