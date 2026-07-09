import os
import tempfile
from io import StringIO
import csv
import json
from io import BytesIO
from pathlib import Path

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from PIL import Image

from accounts.models import CustomUser, Role, UserMembership
from crm.models import Interaction, Opportunity, Task
from core.models import Country, City, Location
from core.models import Currency
from parties.models import Branch, Company, Contact, Address, Department, OperatingEntity, Organization, OrganizationBranding
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


class CustomerSeedCommandTests(TestCase):
    def setUp(self):
        Currency.objects.create(code="USD", name="US Dollar")
        Currency.objects.create(code="PGK", name="Papua New Guinean Kina")

    def _write_csv(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def _read_csv(self, path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_validate_customer_seed_passes_for_valid_files(self):
        customers = self._write_csv(
            "company_name,preferred_quote_currency,payment_term_default\n"
            "Seed Customer,USD,PREPAID\n"
        )
        contacts = self._write_csv(
            "company_name,email,first_name,last_name,is_primary\n"
            "Seed Customer,seed@example.com,Seed,Contact,true\n"
        )

        out = StringIO()
        call_command(
            "validate_customer_seed",
            customers=customers,
            contacts=contacts,
            stdout=out,
        )
        self.assertIn("Validation passed", out.getvalue())

    def test_import_customers_dry_run_does_not_write(self):
        customers = self._write_csv(
            "company_name,preferred_quote_currency,payment_term_default\n"
            "Dry Run Customer,USD,PREPAID\n"
        )

        call_command("import_customers", file=customers, dry_run=True, stdout=StringIO())
        self.assertFalse(Company.objects.filter(name="Dry Run Customer").exists())

    def test_import_customers_creates_company_and_profile(self):
        customers = self._write_csv(
            "company_name,tax_id,preferred_quote_currency,payment_term_default,default_margin_percent,min_margin_percent\n"
            "Seed Customer,TAX-001,USD,PREPAID,15.00,10.00\n"
        )

        call_command("import_customers", file=customers, stdout=StringIO())

        company = Company.objects.get(name="Seed Customer")
        self.assertTrue(company.is_customer)
        self.assertEqual(company.tax_id, "TAX-001")
        self.assertEqual(company.commercial_profile.preferred_quote_currency.code, "USD")
        self.assertEqual(company.commercial_profile.payment_term_default, "PREPAID")

    def test_export_customers_outputs_import_ready_shape(self):
        company = Company.objects.create(
            name="Export Customer",
            is_customer=True,
            is_agent=True,
            company_type="CUSTOMER",
            tax_id="TAX-999",
        )
        call_command(
            "import_customers",
            file=self._write_csv(
                "company_name,preferred_quote_currency,payment_term_default,default_margin_percent,min_margin_percent\n"
                "Export Customer,USD,PREPAID,12.50,8.00\n"
            ),
            stdout=StringIO(),
        )
        output = self._write_csv("company_uuid,company_name\n")

        call_command("export_customers", file=output, stdout=StringIO())

        rows = self._read_csv(output)
        exported = next(row for row in rows if row["company_name"] == "Export Customer")
        self.assertEqual(exported["company_uuid"], str(company.id))
        self.assertEqual(exported["preferred_quote_currency"], "USD")
        self.assertEqual(exported["payment_term_default"], "PREPAID")
        self.assertEqual(exported["is_agent"], "true")

    def test_import_contacts_sets_primary_and_demotes_existing(self):
        company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
        Contact.objects.create(
            company=company,
            first_name="Old",
            last_name="Primary",
            email="old.primary@example.com",
            is_primary=True,
        )

        contacts = self._write_csv(
            "company_name,email,first_name,last_name,is_primary,phone\n"
            "Seed Customer,new.primary@example.com,New,Primary,true,+6751234\n"
        )

        call_command("import_contacts", file=contacts, stdout=StringIO())

        new_contact = Contact.objects.get(email="new.primary@example.com")
        old_contact = Contact.objects.get(email="old.primary@example.com")
        self.assertTrue(new_contact.is_primary)
        self.assertFalse(old_contact.is_primary)
        self.assertTrue(new_contact.is_active)

    def test_import_contacts_inherits_company_scope_for_new_contacts(self):
        organization = Organization.objects.create(name="Scoped Org", slug="scoped-org", is_active=True)
        branch = Branch.objects.create(organization=organization, code="POM", name="Port Moresby")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code="AIR",
            name="Air Freight",
        )
        company = Company.objects.create(
            name="Scoped Customer",
            is_customer=True,
            company_type="CUSTOMER",
            organization=organization,
            branch=branch,
            department=department,
        )

        contacts = self._write_csv(
            "company_uuid,company_name,email,first_name,last_name,is_primary\n"
            f"{company.id},Scoped Customer,scoped.contact@example.com,Scoped,Contact,true\n"
        )

        call_command("import_contacts", file=contacts, stdout=StringIO())

        contact = Contact.objects.get(email="scoped.contact@example.com")
        self.assertEqual(contact.organization, organization)
        self.assertEqual(contact.branch, branch)
        self.assertEqual(contact.department, department)

    def test_import_contacts_matches_existing_email_case_insensitively(self):
        company = Company.objects.create(name="Case Customer", is_customer=True, company_type="CUSTOMER")
        existing = Contact.objects.create(
            company=company,
            first_name="Alice",
            last_name="Original",
            email="Alice@Example.com",
            phone="+6750000",
            is_primary=False,
            is_active=True,
        )

        contacts = self._write_csv(
            "company_name,email,first_name,last_name,is_primary,phone\n"
            "Case Customer,alice@example.com,Alicia,Updated,true,+6751111\n"
        )

        call_command("import_contacts", file=contacts, stdout=StringIO())

        self.assertEqual(Contact.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.first_name, "Alicia")
        self.assertEqual(existing.last_name, "Updated")
        self.assertEqual(existing.phone, "+6751111")
        self.assertTrue(existing.is_primary)

    def test_export_contacts_outputs_import_ready_shape(self):
        company = Company.objects.create(name="Contact Export Customer", is_customer=True, company_type="CUSTOMER")
        Contact.objects.create(
            company=company,
            first_name="Casey",
            last_name="Export",
            email="casey.export@example.com",
            phone="+675123456",
            is_primary=True,
            is_active=True,
        )
        output = self._write_csv("company_uuid,company_name,email,first_name,last_name,full_name,phone,is_primary\n")

        call_command("export_contacts", file=output, stdout=StringIO())

        rows = self._read_csv(output)
        self.assertEqual(len(rows), 1)
        exported = rows[0]
        self.assertEqual(exported["company_name"], "Contact Export Customer")
        self.assertEqual(exported["full_name"], "Casey Export")
        self.assertEqual(exported["is_primary"], "true")

    def test_import_contacts_strict_sync_deactivates_missing(self):
        company = Company.objects.create(name="Sync Customer", is_customer=True, company_type="CUSTOMER")
        keep = Contact.objects.create(
            company=company,
            first_name="Keep",
            last_name="Me",
            email="keep@example.com",
            is_primary=True,
            is_active=True,
        )
        drop = Contact.objects.create(
            company=company,
            first_name="Drop",
            last_name="Me",
            email="drop@example.com",
            is_primary=False,
            is_active=True,
        )

        contacts = self._write_csv(
            "company_name,email,first_name,last_name,is_primary\n"
            "Sync Customer,keep@example.com,Keep,Me,true\n"
        )

        call_command("import_contacts", file=contacts, strict_sync=True, stdout=StringIO())

        keep.refresh_from_db()
        drop.refresh_from_db()
        self.assertTrue(keep.is_active)
        self.assertTrue(keep.is_primary)
        self.assertFalse(drop.is_active)
        self.assertFalse(drop.is_primary)

    def test_import_contacts_strict_sync_matches_email_case_insensitively(self):
        company = Company.objects.create(name="Case Sync Customer", is_customer=True, company_type="CUSTOMER")
        keep = Contact.objects.create(
            company=company,
            first_name="Keep",
            last_name="Me",
            email="Keep@Example.com",
            is_primary=True,
            is_active=True,
        )
        drop = Contact.objects.create(
            company=company,
            first_name="Drop",
            last_name="Me",
            email="drop@example.com",
            is_primary=False,
            is_active=True,
        )

        contacts = self._write_csv(
            "company_name,email,first_name,last_name,is_primary\n"
            "Case Sync Customer,keep@example.com,Keep,Me,true\n"
        )

        call_command("import_contacts", file=contacts, strict_sync=True, stdout=StringIO())

        keep.refresh_from_db()
        drop.refresh_from_db()
        self.assertTrue(keep.is_active)
        self.assertTrue(keep.is_primary)
        self.assertFalse(drop.is_active)
        self.assertFalse(drop.is_primary)

    def test_prepare_customer_seed_csv_transforms_raw_format(self):
        raw = self._write_csv(
            "Organization,\"Full Name (First, Last)\",Position,Email,City,State,Country\n"
            "Air Niugini Limited,Daisy Pumwa,Purchasing Manager,dpumwa@airniugini.com.pg,Port Moresby,NCD,PG\n"
            "Air Niugini Limited,James Tira,Manager,jtira@airniugini.com.pg,Port Moresby,NCD,PG\n"
            "Able Home & Office,Alona Evangelista,Branch Manager,bm@pom.able.com.pg,Port Moresby,NCD,PG\n"
        )
        customers_out = self._write_csv("company_name\n")
        contacts_out = self._write_csv("company_name,full_name,email,is_primary,city,state,country\n")

        call_command(
            "prepare_customer_seed_csv",
            input=raw,
            customers_out=customers_out,
            contacts_out=contacts_out,
            stdout=StringIO(),
        )

        customers = self._read_csv(customers_out)
        contacts = self._read_csv(contacts_out)

        self.assertEqual(len(customers), 2)
        self.assertEqual(len(contacts), 3)
        self.assertEqual(customers[0]["company_name"], "Air Niugini Limited")
        self.assertEqual(contacts[0]["is_primary"], "true")
        self.assertEqual(contacts[1]["is_primary"], "false")

    def test_prepare_customer_seed_csv_writes_issue_report(self):
        raw = self._write_csv(
            "Organization,\"Full Name (First, Last)\",Position,Email,City,State,Country\n"
            "Air Niugini Limited,Daisy Pumwa,Purchasing Manager,dpumwa@airniugini.com.pg,Port Moresby,NCD,PG\n"
            "Air Niugini Limited,Duplicate,Purchasing Manager,dpumwa@airniugini.com.pg,Port Moresby,NCD,PG\n"
            "Able Home & Office,No Email,Branch Manager,,Port Moresby,NCD,PG\n"
        )
        customers_out = self._write_csv("company_name\n")
        contacts_out = self._write_csv("company_name,full_name,email,is_primary,city,state,country\n")
        issues_out = self._write_csv("row_number,reason,organization,full_name,email,city,state,country\n")

        call_command(
            "prepare_customer_seed_csv",
            input=raw,
            customers_out=customers_out,
            contacts_out=contacts_out,
            report_out=issues_out,
            stdout=StringIO(),
        )

        issues = self._read_csv(issues_out)
        reasons = {issue["reason"] for issue in issues}
        self.assertEqual(len(issues), 2)
        self.assertIn("duplicate_email_in_input", reasons)
        self.assertIn("missing_organization_or_email", reasons)


class CustomerContactRBACReportTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_customer_contact_report", *args, stdout=stdout)
        return stdout.getvalue()

    def test_report_counts_safe_customer_contact_scope_signals(self):
        customer = Company.objects.create(name="Report Customer", is_customer=True, company_type="CUSTOMER")
        Company.objects.create(name="Report Supplier", company_type="SUPPLIER")
        contact = Contact.objects.create(
            company=customer,
            first_name="Safe",
            last_name="Contact",
            email="safe.contact@example.com",
            phone="+675000",
        )
        quote = Quote.objects.create(customer=customer, contact=contact, mode="AIR")
        SpotPricingEnvelopeDB.objects.create(
            quote=quote,
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={"origin_country": "PG", "destination_country": "PG"},
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test SPE",
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

        payload = json.loads(self._call_report("--format", "json"))

        summary = payload["summary"]
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(summary["total_companies"], 2)
        self.assertEqual(summary["customer_companies"], 1)
        self.assertEqual(summary["total_contacts"], 1)
        self.assertEqual(summary["companies_with_quotes"], 1)
        self.assertEqual(summary["companies_with_spot"], 1)
        self.assertEqual(summary["contacts_with_quotes"], 1)

    def test_show_details_omits_contact_email_phone_and_commercial_fields(self):
        customer = Company.objects.create(name="Detail Customer", is_customer=True, company_type="CUSTOMER")
        Contact.objects.create(
            company=customer,
            first_name="Hidden",
            last_name="Email",
            email="hidden.email@example.com",
            phone="+675111",
        )

        output = self._call_report("--show-details")

        self.assertIn("Detail Customer", output)
        self.assertIn("Hidden Email", output)
        self.assertNotIn("hidden.email@example.com", output)
        self.assertNotIn("+675111", output)
        self.assertNotIn("margin", output.lower())


class CustomerCrmBackfillReportTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_customer_crm_backfill_report", *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self, suffix=""):
        organization = Organization.objects.create(
            name=f"Backfill Org {suffix}".strip(),
            slug=f"backfill-org-{suffix or 'default'}",
            is_active=True,
        )
        branch = Branch.objects.create(organization=organization, code=f"POM{suffix}"[:16], name="Port Moresby")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code=f"AIR{suffix}"[:24],
            name="Air Freight",
        )
        return organization, branch, department

    def _role(self, code="sales"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_parent_scope_candidates_are_detected(self):
        organization, branch, department = self._scope("parent")
        company = Company.objects.create(
            name="Parent Scoped Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        Contact.objects.create(
            company=company,
            first_name="Parent",
            last_name="Contact",
            email="parent.scope@example.com",
        )

        payload = json.loads(self._call_report("--format", "json", "--show-details"))

        contact = next(row for row in payload["models"]["contact"]["details"] if row["label"] == "Parent Contact")
        self.assertEqual(contact["candidate_source"], "parent_scope")
        self.assertEqual(contact["unresolved_fields"], [])

    def test_single_membership_fallback_is_detected(self):
        organization, branch, department = self._scope("single")
        user = CustomUser.objects.create_user(username="single-owner", password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=self._role("single-role"),
        )
        Company.objects.create(name="Owned Customer", account_owner=user)

        payload = json.loads(self._call_report("--format", "json", "--show-details"))

        company = next(row for row in payload["models"]["company"]["details"] if row["label"] == "Owned Customer")
        self.assertEqual(company["candidate_source"], "single_membership")
        self.assertEqual(company["unresolved_fields"], [])

    def test_multiple_membership_ambiguity_is_reported_safely(self):
        organization, branch, department = self._scope("multi")
        other_branch = Branch.objects.create(organization=organization, code="LAE", name="Lae")
        other_department = Department.objects.create(
            organization=organization,
            branch=other_branch,
            code="SEA",
            name="Sea Freight",
        )
        user = CustomUser.objects.create_user(username="multi-owner", password="x")
        role = self._role("multi-role")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
            is_primary=True,
        )
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=other_branch,
            department=other_department,
            role=role,
            is_primary=False,
        )
        Company.objects.create(name="Ambiguous Customer", account_owner=user)

        payload = json.loads(self._call_report("--format", "json", "--show-details"))

        company = next(row for row in payload["models"]["company"]["details"] if row["label"] == "Ambiguous Customer")
        self.assertEqual(company["candidate_source"], "shared_memberships")
        self.assertEqual(company["unresolved_fields"], ["branch", "department"])
        self.assertEqual(company["ambiguity_reason"], "multiple_memberships_shared_values_only")

    def test_unsafe_text_fields_are_not_used_for_inference(self):
        company = Company.objects.create(name="AIR POM Customer")
        Opportunity.objects.create(
            company=company,
            title="AIR POM department lane",
            service_type="AIR",
            origin="POM",
            destination="LAE",
        )

        payload = json.loads(self._call_report("--format", "json", "--show-details"))

        opportunity = next(row for row in payload["models"]["opportunity"]["details"] if row["label"] == "AIR POM department lane")
        self.assertEqual(opportunity["candidate_source"], "unresolved")
        self.assertEqual(opportunity["unresolved_fields"], ["organization", "branch", "department"])

    def test_show_details_omits_sensitive_crm_content(self):
        company = Company.objects.create(name="Sensitive Customer")
        opportunity = Opportunity.objects.create(
            company=company,
            title="Sensitive opportunity title",
            service_type="AIR",
        )
        Interaction.objects.create(
            company=company,
            opportunity=opportunity,
            interaction_type=Interaction.InteractionType.CALL,
            summary="Do not leak this interaction summary",
            outcomes="Do not leak this outcome",
        )
        Task.objects.create(
            company=company,
            owner=CustomUser.objects.create_user(username="task-owner", password="x"),
            description="Do not leak this task description",
            due_date=timezone.now().date(),
        )

        output = self._call_report("--show-details")

        self.assertIn("Sensitive opportunity title", output)
        self.assertNotIn("Do not leak this interaction summary", output)
        self.assertNotIn("Do not leak this outcome", output)
        self.assertNotIn("Do not leak this task description", output)


class HistoricalScopeBackfillPlanTests(TestCase):
    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_historical_scope_backfill_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self, suffix=""):
        organization = Organization.objects.create(
            name=f"Historical Org {suffix}".strip(),
            slug=f"historical-org-{suffix or 'default'}",
            is_active=True,
        )
        branch = Branch.objects.create(organization=organization, code=f"H{suffix}"[:16], name="Historical Branch")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code=f"HD{suffix}"[:24],
            name="Historical Department",
        )
        return organization, branch, department

    def _role(self, code="historical-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def _member(self, username, suffix=""):
        organization, branch, department = self._scope(suffix or username)
        user = CustomUser.objects.create_user(username=username, password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=self._role(f"{username}-role"[:32]),
        )
        return user

    def test_read_only_command_does_not_write(self):
        user = self._member("readonly-owner")
        company = Company.objects.create(name="Read Only Customer", account_owner=user)

        before = (company.organization_id, company.branch_id, company.department_id)
        payload = json.loads(self._call_plan("--format", "json"))

        company.refresh_from_db()
        self.assertFalse(payload["write_enabled"])
        self.assertEqual((company.organization_id, company.branch_id, company.department_id), before)

    def test_complete_records_are_counted(self):
        organization, branch, department = self._scope("complete")
        Company.objects.create(
            name="Complete Historical Customer",
            organization=organization,
            branch=branch,
            department=department,
        )

        payload = json.loads(self._call_plan("--format", "json"))

        self.assertEqual(payload["models"]["Company"]["summary"]["records_complete"], 1)
        self.assertEqual(payload["models"]["Company"]["summary"]["records_missing_organization"], 0)

    def test_missing_scope_with_complete_owner_membership_is_backfillable(self):
        user = self._member("owner-backfill")
        Company.objects.create(name="Owner Backfill Customer", account_owner=user)

        payload = json.loads(self._call_plan("--format", "json"))

        summary = payload["models"]["Company"]["summary"]
        self.assertEqual(summary["records_backfillable_from_owner_membership"], 1)
        self.assertEqual(summary["records_blocked_no_safe_evidence"], 0)

    def test_missing_scope_with_complete_parent_scope_is_backfillable(self):
        organization, branch, department = self._scope("parent")
        company = Company.objects.create(
            name="Parent Scope Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        Contact.objects.create(company=company, first_name="Parent", last_name="Contact", email="phase9a-parent@example.com")

        payload = json.loads(self._call_plan("--format", "json"))

        summary = payload["models"]["Contact"]["summary"]
        self.assertEqual(summary["records_backfillable_from_parent_scope"], 1)

    def test_owner_derived_parent_scope_does_not_create_new_apply_candidate(self):
        owner = self._member("owner-derived-parent")
        organization, branch, department = self._scope("owner-derived-parent-scope")
        company = Company.objects.create(
            name="Owner Derived Parent Scope Customer",
            account_owner=owner,
            organization=organization,
            branch=branch,
            department=department,
        )
        Contact.objects.create(
            company=company,
            first_name="Owner",
            last_name="Derived",
            email="phase9a-owner-derived@example.com",
        )

        payload = json.loads(self._call_plan("--format", "json"))

        contact = payload["models"]["Contact"]
        self.assertEqual(contact["summary"]["records_backfillable_from_parent_scope"], 0)
        self.assertEqual(contact["summary"]["records_blocked_no_safe_evidence"], 1)

    def test_multiple_owner_memberships_are_blocked(self):
        organization, branch, department = self._scope("multi")
        other_branch = Branch.objects.create(organization=organization, code="H2", name="Second Branch")
        other_department = Department.objects.create(
            organization=organization,
            branch=other_branch,
            code="HD2",
            name="Second Department",
        )
        user = CustomUser.objects.create_user(username="multi-historical", password="x")
        role = self._role("multi-historical-role")
        UserMembership.objects.create(user=user, organization=organization, branch=branch, department=department, role=role)
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=other_branch,
            department=other_department,
            role=role,
            is_primary=False,
        )
        Company.objects.create(name="Multi Owner Customer", account_owner=user)

        payload = json.loads(self._call_plan("--format", "json"))

        company = payload["models"]["Company"]
        self.assertEqual(company["summary"]["records_blocked_owner_multiple_active_memberships"], 1)
        self.assertEqual(company["sample_blocked_records"][0]["blocker_reason"], "multiple_owner_memberships")

    def test_no_owner_membership_is_blocked(self):
        user = CustomUser.objects.create_user(username="no-membership-historical", password="x")
        Company.objects.create(name="No Membership Customer", account_owner=user)

        payload = json.loads(self._call_plan("--format", "json"))

        summary = payload["models"]["Company"]["summary"]
        self.assertEqual(summary["records_blocked_owner_no_active_membership"], 1)

    def test_incomplete_parent_scope_is_blocked(self):
        organization, _branch, _department = self._scope("partial-parent")
        company = Company.objects.create(name="Partial Parent Customer", organization=organization)
        Contact.objects.create(company=company, first_name="Partial", last_name="Parent", email="phase9a-partial@example.com")

        payload = json.loads(self._call_plan("--format", "json"))

        contact = payload["models"]["Contact"]
        self.assertEqual(contact["summary"]["records_blocked_parent_scope_incomplete"], 1)
        self.assertEqual(contact["sample_blocked_records"][0]["parent_evidence"]["missing_scope"], ["branch", "department"])

    def test_json_output_and_readiness_classify_manual_review(self):
        Company.objects.create(name="Manual Review Customer")

        payload = json.loads(self._call_plan("--format", "json"))

        self.assertIn("Company", payload["models"])
        self.assertEqual(payload["models"]["Company"]["sample_blocked_records"][0]["blocker_reason"], "no_safe_evidence")
        self.assertEqual(payload["readiness_status"], "READY_WITH_MANUAL_REVIEW_EXCLUSIONS")
        self.assertEqual(payload["summary"]["manual_review_required"], 1)
        self.assertEqual(payload["proposed_apply_strategy"]["apply_eligible_records"], 0)
        self.assertEqual(payload["proposed_apply_strategy"]["manual_review_excluded_records"], 1)
        self.assertIn("no_safe_evidence", payload["proposed_apply_strategy"]["excluded_blocker_reasons"])

    def test_fully_backfillable_data_is_ready_for_apply(self):
        user = self._member("fully-ready-owner")
        Company.objects.create(name="Fully Ready Customer", account_owner=user)

        payload = json.loads(self._call_plan("--format", "json"))

        self.assertEqual(payload["readiness_status"], "READY_FOR_BACKFILL_APPLY")
        self.assertEqual(payload["proposed_apply_strategy"]["apply_eligible_records"], 1)
        self.assertEqual(payload["proposed_apply_strategy"]["manual_review_excluded_records"], 0)

    def test_unclassified_summary_is_not_ready_for_apply(self):
        from parties.management.commands.rbac_historical_scope_backfill_plan import empty_summary, readiness_status

        summary = empty_summary()
        summary["manual_review_required"] = 0
        summary["unclassified_records"] = 1

        self.assertEqual(readiness_status(summary), "NOT_READY_FOR_BACKFILL_APPLY")

    def test_text_output_reports_apply_strategy(self):
        user = self._member("text-ready-owner")
        Company.objects.create(name="Text Ready Customer", account_owner=user)
        Company.objects.create(name="Text Manual Review Customer")

        output = self._call_plan()

        self.assertIn("safe apply candidates=1", output)
        self.assertIn("manual-review exclusions=1", output)
        self.assertIn("Next apply command must exclude manual-review records", output)


class HistoricalScopeBackfillApplyTests(TestCase):
    def _call_apply(self, *args):
        stdout = StringIO()
        call_command("rbac_historical_scope_backfill_apply", *args, stdout=stdout)
        return stdout.getvalue()

    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_historical_scope_backfill_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self, suffix=""):
        organization = Organization.objects.create(
            name=f"Apply Org {suffix}".strip(),
            slug=f"apply-org-{suffix or 'default'}",
            is_active=True,
        )
        branch = Branch.objects.create(organization=organization, code=f"A{suffix}"[:16], name="Apply Branch")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code=f"AD{suffix}"[:24],
            name="Apply Department",
        )
        return organization, branch, department

    def _role(self, code="apply-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def _member(self, username, suffix=""):
        organization, branch, department = self._scope(suffix or username)
        user = CustomUser.objects.create_user(username=username, password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=self._role(f"{username}-role"[:32]),
        )
        return user, organization, branch, department

    def test_dry_run_does_not_write(self):
        user, _organization, _branch, _department = self._member("dry-run-owner")
        company = Company.objects.create(name="Dry Run Apply Customer", account_owner=user)

        payload = json.loads(self._call_apply("--format", "json"))

        company.refresh_from_db()
        self.assertEqual(payload["models"]["Company"]["summary"]["planned"], 1)
        self.assertIsNone(company.organization_id)
        self.assertIsNone(company.branch_id)
        self.assertIsNone(company.department_id)

    def test_apply_backfills_company_from_account_owner_membership(self):
        user, organization, branch, department = self._member("company-owner")
        company = Company.objects.create(name="Company Owner Apply Customer", account_owner=user)

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        company.refresh_from_db()
        self.assertEqual(payload["models"]["Company"]["summary"]["applied"], 1)
        self.assertEqual(company.organization, organization)
        self.assertEqual(company.branch, branch)
        self.assertEqual(company.department, department)

    def test_apply_backfills_contact_from_parent_company_scope(self):
        organization, branch, department = self._scope("contact-parent")
        company = Company.objects.create(
            name="Contact Parent Apply Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        contact = Contact.objects.create(
            company=company,
            first_name="Apply",
            last_name="Contact",
            email="phase9b-contact@example.com",
        )

        self._call_apply("--apply")

        contact.refresh_from_db()
        self.assertEqual(contact.organization, organization)
        self.assertEqual(contact.branch, branch)
        self.assertEqual(contact.department, department)

    def test_apply_uses_preflight_plan_and_does_not_cascade_parent_backfill(self):
        user, organization, branch, department = self._member("preflight-owner")
        company = Company.objects.create(name="Preflight Parent Apply Customer", account_owner=user)
        contact = Contact.objects.create(
            company=company,
            first_name="Preflight",
            last_name="Contact",
            email="phase9b-preflight@example.com",
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        company.refresh_from_db()
        contact.refresh_from_db()
        self.assertEqual(payload["models"]["Company"]["summary"]["applied"], 1)
        self.assertEqual(payload["models"]["Contact"]["summary"]["applied"], 0)
        self.assertEqual(company.organization, organization)
        self.assertEqual(company.branch, branch)
        self.assertEqual(company.department, department)
        self.assertIsNone(contact.organization_id)
        self.assertIsNone(contact.branch_id)
        self.assertIsNone(contact.department_id)

    def test_apply_backfills_crm_models_from_safe_owner_or_parent_evidence(self):
        owner, organization, branch, department = self._member("crm-owner")
        company = Company.objects.create(
            name="CRM Parent Apply Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        opportunity = Opportunity.objects.create(
            company=company,
            title="Owner scoped opportunity",
            service_type="AIR",
            owner=owner,
        )
        interaction = Interaction.objects.create(
            company=company,
            opportunity=opportunity,
            author=owner,
            interaction_type=Interaction.InteractionType.CALL,
            summary="Hidden body",
        )
        task = Task.objects.create(
            company=company,
            opportunity=opportunity,
            owner=owner,
            due_date=timezone.now().date(),
            description="Hidden task body",
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        for record in (opportunity, interaction, task):
            record.refresh_from_db()
            self.assertEqual(record.organization, organization)
            self.assertEqual(record.branch, branch)
            self.assertEqual(record.department, department)
        self.assertEqual(payload["models"]["Opportunity"]["summary"]["applied"], 1)
        self.assertEqual(payload["models"]["Interaction"]["summary"]["applied"], 1)
        self.assertEqual(payload["models"]["Task"]["summary"]["applied"], 1)

    def test_apply_excludes_manual_review_records(self):
        organization, _branch, _department = self._scope("manual")
        no_member = CustomUser.objects.create_user(username="apply-no-member", password="x")
        multi_user = CustomUser.objects.create_user(username="apply-multi", password="x")
        role = self._role("apply-multi-role")
        branch_one = Branch.objects.create(organization=organization, code="M1", name="Manual One")
        branch_two = Branch.objects.create(organization=organization, code="M2", name="Manual Two")
        department_one = Department.objects.create(organization=organization, branch=branch_one, code="MD1", name="Manual One")
        department_two = Department.objects.create(organization=organization, branch=branch_two, code="MD2", name="Manual Two")
        UserMembership.objects.create(user=multi_user, organization=organization, branch=branch_one, department=department_one, role=role)
        UserMembership.objects.create(
            user=multi_user,
            organization=organization,
            branch=branch_two,
            department=department_two,
            role=role,
            is_primary=False,
        )
        no_safe = Company.objects.create(name="No Evidence Apply Customer")
        owner_none = Company.objects.create(name="No Membership Apply Customer", account_owner=no_member)
        owner_multi = Company.objects.create(name="Multi Membership Apply Customer", account_owner=multi_user)
        partial_parent = Company.objects.create(name="Partial Parent Apply Customer", organization=organization)
        contact = Contact.objects.create(
            company=partial_parent,
            first_name="Partial",
            last_name="Apply",
            email="phase9b-partial@example.com",
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        for record in (no_safe, owner_none, owner_multi, partial_parent, contact):
            record.refresh_from_db()
            self.assertIsNone(record.branch_id)
            self.assertIsNone(record.department_id)
        self.assertEqual(payload["summary"]["skipped"], 5)
        self.assertEqual(payload["summary"]["applied"], 0)

    def test_apply_is_idempotent_and_does_not_overwrite_complete_scope(self):
        user, owner_org, owner_branch, owner_department = self._member("idempotent-owner")
        existing_org, existing_branch, existing_department = self._scope("existing")
        company = Company.objects.create(name="Idempotent Apply Customer", account_owner=user)
        contact = Contact.objects.create(
            company=company,
            first_name="Idempotent",
            last_name="Contact",
            email="phase9b-idempotent@example.com",
        )
        complete = Company.objects.create(
            name="Already Complete Apply Customer",
            account_owner=user,
            organization=existing_org,
            branch=existing_branch,
            department=existing_department,
        )

        first = json.loads(self._call_apply("--apply", "--format", "json"))
        second = json.loads(self._call_apply("--apply", "--format", "json"))

        complete.refresh_from_db()
        contact.refresh_from_db()
        self.assertEqual(first["models"]["Company"]["summary"]["applied"], 1)
        self.assertEqual(second["models"]["Company"]["summary"]["applied"], 0)
        self.assertEqual(second["models"]["Contact"]["summary"]["applied"], 0)
        self.assertIsNone(contact.organization_id)
        self.assertIsNone(contact.branch_id)
        self.assertIsNone(contact.department_id)
        self.assertEqual(complete.organization, existing_org)
        self.assertNotEqual(complete.organization, owner_org)
        self.assertNotEqual(complete.branch, owner_branch)
        self.assertNotEqual(complete.department, owner_department)

    def test_json_output_includes_counts_and_post_apply_plan_improves(self):
        user, _organization, _branch, _department = self._member("plan-improves-owner")
        Company.objects.create(name="Plan Improves Apply Customer", account_owner=user)

        before = json.loads(self._call_plan("--format", "json"))
        payload = json.loads(self._call_apply("--apply", "--format", "json"))
        after = json.loads(self._call_plan("--format", "json"))

        self.assertIn("applied", payload["models"]["Company"]["summary"])
        self.assertEqual(before["proposed_apply_strategy"]["apply_eligible_records"], 1)
        self.assertEqual(after["summary"]["records_complete"], 1)
        self.assertEqual(after["proposed_apply_strategy"]["apply_eligible_records"], 0)


class EnforcementReadinessReportTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_enforcement_readiness_report", *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self, suffix=""):
        organization = Organization.objects.create(
            name=f"Enforcement Org {suffix}".strip(),
            slug=f"enforcement-org-{suffix or 'default'}",
            is_active=True,
        )
        branch = Branch.objects.create(organization=organization, code=f"E{suffix}"[:16], name="Enforcement Branch")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code=f"ED{suffix}"[:24],
            name="Enforcement Department",
        )
        return organization, branch, department

    def _member(self, username):
        organization, branch, department = self._scope(username)
        role = Role.objects.create(code=f"{username}-role"[:32], name=username, is_system=True)
        user = CustomUser.objects.create_user(username=username, password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
        )
        return user, organization, branch, department

    def test_command_is_read_only(self):
        user, _organization, _branch, _department = self._member("enforcement-readonly")
        company = Company.objects.create(name="Enforcement Readonly Customer", account_owner=user)

        payload = json.loads(self._call_report("--format", "json"))

        company.refresh_from_db()
        self.assertFalse(payload["write_enabled"])
        self.assertIsNone(company.organization_id)
        self.assertIsNone(company.branch_id)
        self.assertIsNone(company.department_id)

    def test_reports_complete_missing_and_manual_review_counts(self):
        organization, branch, department = self._scope("complete")
        Company.objects.create(
            name="Complete Enforcement Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        Company.objects.create(name="Manual Enforcement Customer")

        payload = json.loads(self._call_report("--format", "json"))

        post = payload["post_backfill"]
        self.assertEqual(post["summary"]["records_complete"], 1)
        self.assertEqual(post["summary"]["records_missing_organization"], 1)
        self.assertEqual(post["manual_review_excluded_records"], 1)
        self.assertEqual(post["models"]["Company"]["manual_review_exclusions"]["no_safe_evidence"], 1)

    def test_apply_candidates_make_report_not_ready(self):
        user, _organization, _branch, _department = self._member("enforcement-candidate")
        Company.objects.create(name="Candidate Enforcement Customer", account_owner=user)

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["post_backfill"]["apply_eligible_records"], 1)
        self.assertEqual(payload["readiness_status"], "NOT_READY_FOR_ENFORCEMENT_DESIGN")
        self.assertIn("apply_eligible_records_remaining", payload["readiness_blockers"])

    def test_json_reports_surfaces_and_ready_status(self):
        Company.objects.create(name="Manual Only Enforcement Customer")

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["readiness_status"], "READY_FOR_ENFORCEMENT_DESIGN")
        self.assertTrue(payload["enforcement_surfaces"])
        self.assertEqual(payload["global_or_unfiltered_surfaces"], [])
        self.assertIn("proposed_enforcement_rules", payload)
        self.assertIn("admin_override_considerations", payload)


class ScopeCompletenessReportTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_scope_completeness_report", *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self, suffix=""):
        organization = Organization.objects.create(
            name=f"Completeness Org {suffix}".strip(),
            slug=f"completeness-org-{suffix or 'default'}",
            is_active=True,
        )
        branch = Branch.objects.create(organization=organization, code=f"C{suffix}"[:16], name="Completeness Branch")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code=f"D{suffix}"[:24],
            name="Completeness Department",
        )
        return organization, branch, department

    def _role(self, code="scope-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_readiness_calculation_reports_missing_branch_not_ready(self):
        organization, _, department = self._scope("ready")
        Company.objects.create(
            name="Org Department Only Customer",
            organization=organization,
            department=department,
        )

        payload = json.loads(self._call_report("--format", "json"))

        readiness = payload["readiness"]
        self.assertEqual(readiness["organization_readiness_percent"], 100.0)
        self.assertEqual(readiness["department_readiness_percent"], 100.0)
        self.assertEqual(readiness["branch_readiness_percent"], 0.0)
        self.assertEqual(readiness["overall"], "NOT READY FOR BACKFILL")

    def test_branch_coverage_calculates_scope_shapes(self):
        organization, branch, department = self._scope("coverage")
        Company.objects.create(name="Org Only Customer", organization=organization)
        Company.objects.create(name="Org Department Customer", organization=organization, department=department)
        Company.objects.create(name="Org Branch Customer", organization=organization, branch=branch)
        Company.objects.create(
            name="Complete Customer",
            organization=organization,
            branch=branch,
            department=department,
        )
        Company.objects.create(name="No Scope Customer")

        payload = json.loads(self._call_report("--format", "json"))

        company = payload["branch_coverage"]["company"]
        self.assertEqual(company["organization_only"], 1)
        self.assertEqual(company["organization_department"], 1)
        self.assertEqual(company["organization_branch"], 1)
        self.assertEqual(company["organization_branch_department"], 1)
        self.assertEqual(company["no_scope"], 1)

    def test_membership_analysis_counts_referenced_users(self):
        organization, branch, department = self._scope("member")
        role = self._role("member-role")
        single = CustomUser.objects.create_user(username="single-member", password="x")
        none = CustomUser.objects.create_user(username="no-member", password="x")
        UserMembership.objects.create(
            user=single,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
        )
        Company.objects.create(name="Single Member Customer", account_owner=single)
        Task.objects.create(
            company=Company.objects.create(name="No Member Customer"),
            owner=none,
            due_date=timezone.now().date(),
            description="Hidden task body",
        )

        payload = json.loads(self._call_report("--format", "json"))

        membership = payload["membership_coverage"]
        self.assertEqual(membership["referenced_users"], 2)
        self.assertEqual(membership["users_with_one_active_membership"], 1)
        self.assertEqual(membership["users_with_multiple_memberships"], 0)
        self.assertEqual(membership["users_with_no_memberships"], 1)
        self.assertEqual(membership["branch_populated"], 1)

    def test_quote_coverage_counts_linked_quote_scope(self):
        organization, branch, department = self._scope("quote")
        company = Company.objects.create(name="Quoted Customer")
        opportunity = Opportunity.objects.create(company=company, title="Quoted", service_type="AIR")
        Quote.objects.create(customer=company, opportunity=opportunity, mode="AIR", organization=organization)
        Quote.objects.create(
            customer=company,
            opportunity=opportunity,
            mode="SEA",
            organization=organization,
            branch=branch,
            department=department,
        )

        payload = json.loads(self._call_report("--format", "json"))

        quote = payload["quote_coverage"]
        self.assertEqual(quote["linked_quotes"], 2)
        self.assertEqual(quote["organization_only"], 1)
        self.assertEqual(quote["organization_branch_department"], 1)
        self.assertGreaterEqual(payload["branch_discovery"]["quote_scope"]["complete_count"], 1)

    def test_show_details_omits_sensitive_crm_content(self):
        company = Company.objects.create(name="Completeness Sensitive Customer")
        opportunity = Opportunity.objects.create(
            company=company,
            title="Completeness safe title",
            service_type="AIR",
        )
        Interaction.objects.create(
            company=company,
            opportunity=opportunity,
            interaction_type=Interaction.InteractionType.EMAIL,
            summary="Sensitive completeness interaction summary",
            outcomes="Sensitive completeness outcome",
        )
        Task.objects.create(
            company=company,
            owner=CustomUser.objects.create_user(username="completeness-task-owner", password="x"),
            description="Sensitive completeness task description",
            due_date=timezone.now().date(),
        )

        output = self._call_report("--show-details")

        self.assertIn("Completeness safe title", output)
        self.assertNotIn("Sensitive completeness interaction summary", output)
        self.assertNotIn("Sensitive completeness outcome", output)
        self.assertNotIn("Sensitive completeness task description", output)


class RBACHierarchyReportTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_hierarchy_report", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="hierarchy-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_report_identifies_missing_tenant_model_and_organization_role(self):
        payload = json.loads(self._call_report("--format", "json"))

        self.assertFalse(payload["write_enabled"])
        self.assertFalse(payload["model_assessment"]["tenant_model_exists"])
        self.assertIn("workspace", payload["model_assessment"]["organization_role"])
        self.assertTrue(payload["model_assessment"]["can_represent_intended_hierarchy"])

    def test_report_detects_intended_hierarchy_mismatches(self):
        organization = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        efm_png = OperatingEntity.objects.create(
            organization=organization,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        Branch.objects.create(organization=organization, operating_entity=efm_png, code="POM", name="Port Moresby")
        Organization.objects.create(name="Legacy Workspace", slug="legacy-workspace")

        payload = json.loads(self._call_report("--format", "json"))

        mismatches = payload["mismatches"]
        self.assertNotIn("EFM PNG", mismatches["missing_operating_entities"])
        self.assertIn("EFM Australia", mismatches["missing_operating_entities"])
        self.assertIn("Legacy Workspace", mismatches["extra_organizations"])
        self.assertIn("Lae", mismatches["missing_branches_by_entity"]["EFM PNG"])

    def test_report_counts_active_memberships_missing_branch(self):
        organization = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        department = Department.objects.create(organization=organization, code="AIR", name="Air Freight")
        user = CustomUser.objects.create_user(username="branchless-user", email="branchless@example.com", password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            department=department,
            role=self._role("branchless-role"),
        )

        payload = json.loads(self._call_report("--format", "json", "--show-details"))

        self.assertEqual(payload["summary"]["active_memberships_missing_branch"], 1)
        self.assertEqual(payload["membership_summary"]["active_missing_branch"], 1)
        self.assertEqual(payload["answers"]["are_active_memberships_missing_branch"], "yes")
        membership = payload["details"]["memberships"][0]
        self.assertEqual(membership["username"], "branchless-user")
        self.assertIsNone(membership["branch"])

    def test_show_details_uses_safe_hierarchy_fields_only(self):
        organization = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=organization,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        branch = Branch.objects.create(organization=organization, operating_entity=entity, code="POM", name="Port Moresby")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code="AIR",
            name="Air Freight",
        )
        user = CustomUser.objects.create_user(username="safe-user", email="safe@example.com", password="x")
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=self._role("safe-role"),
        )

        output = self._call_report("--show-details")

        self.assertIn("safe-user", output)
        self.assertIn("safe@example.com", output)
        self.assertIn("Port Moresby", output)
        self.assertNotIn("password", output.lower())
        self.assertNotIn("quote payload", output.lower())
        self.assertNotIn("pricing", output.lower())


class MasterDataAlignmentPlanTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_master_data_alignment_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="alignment-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_detects_missing_target_organizations_and_legacy_orgs(self):
        Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        Organization.objects.create(name="Test Org", slug="test-org")

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("EFM PNG", payload["organizations"]["missing"])
        actions = {row["name"]: row["action"] for row in payload["organizations"]["actions"]}
        self.assertEqual(actions["Express Freight Management"], "RENAME_CANDIDATE")
        self.assertEqual(actions["Test Org"], "EXCLUDE_TEST")

    def test_detects_missing_branch_and_readiness(self):
        Organization.objects.create(name="EFM PNG", slug="efm-png")

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("Port Moresby", payload["branches"]["missing"]["EFM PNG"])
        self.assertIn("Lae", payload["branches"]["missing"]["EFM PNG"])
        self.assertEqual(payload["readiness"]["seed_planning"], "READY_FOR_ADDITIVE_SEED_PLANNING")
        self.assertEqual(payload["readiness"]["historical_backfill"], "NOT_READY_FOR_HISTORICAL_BACKFILL")

    def test_counts_membership_gaps_and_multiple_memberships(self):
        organization = Organization.objects.create(name="EFM PNG", slug="efm-png")
        branch = Branch.objects.create(organization=organization, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=organization, code="AIR", name="Air Freight")
        role = self._role()
        complete_user = CustomUser.objects.create_user(username="complete-user", email="complete@example.com")
        multi_user = CustomUser.objects.create_user(username="multi-user", email="multi@example.com")
        UserMembership.objects.create(
            user=complete_user,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
        )
        UserMembership.objects.create(user=multi_user, organization=organization, role=role)
        UserMembership.objects.create(
            user=multi_user,
            organization=organization,
            branch=branch,
            role=role,
            is_primary=False,
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["active_memberships"], 3)
        self.assertEqual(payload["memberships"]["missing_branch"], 1)
        self.assertEqual(payload["memberships"]["missing_department"], 2)
        self.assertEqual(payload["memberships"]["complete_membership"], 1)
        self.assertEqual(payload["memberships"]["users_with_multiple_active_memberships"], 1)
        self.assertIn("active memberships missing branch: 1", payload["blockers"])

    def test_show_details_uses_safe_identity_fields_only(self):
        organization = Organization.objects.create(name="EFM PNG", slug="efm-png")
        role = self._role("safe-alignment-role")
        user = CustomUser.objects.create_user(
            username="safe-alignment-user",
            email="safe-alignment@example.com",
            password="do-not-leak",
        )
        UserMembership.objects.create(user=user, organization=organization, role=role)

        output = self._call_report("--show-details")

        self.assertIn("safe-alignment-user", output)
        self.assertIn("safe-alignment@example.com", output)
        self.assertNotIn("do-not-leak", output)
        self.assertNotIn("customer name", output.lower())
        self.assertNotIn("route", output.lower())
        self.assertNotIn("pricing", output.lower())


class MasterDataSeedAlignmentTests(TestCase):
    def _call_command(self, *args):
        stdout = StringIO()
        call_command("rbac_master_data_seed_alignment", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="seed-alignment-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_dry_run_does_not_create_master_data(self):
        output = self._call_command()

        self.assertIn("Mode: dry-run", output)
        self.assertFalse(Organization.objects.filter(name="EFM PNG").exists())
        self.assertFalse(Branch.objects.filter(name="Port Moresby").exists())
        self.assertFalse(Department.objects.filter(name="Air Freight").exists())

    def test_apply_creates_only_canonical_master_data(self):
        legacy_eac_count = Organization.objects.filter(name="EFM Express Air Cargo").count()
        output = self._call_command("--apply")

        self.assertIn("Mode: apply", output)
        self.assertTrue(Organization.objects.filter(name="EFM PNG").exists())
        self.assertTrue(Branch.objects.filter(organization__name="EFM PNG", name="Port Moresby").exists())
        self.assertTrue(Branch.objects.filter(organization__name="EFM Solomon Islands", name="Honiara").exists())
        self.assertTrue(Department.objects.filter(organization__name="EFM Fiji", name="Customs").exists())
        self.assertEqual(Organization.objects.filter(name="EFM Express Air Cargo").count(), legacy_eac_count)
        self.assertFalse(Department.objects.filter(name="EAC").exists())
        self.assertFalse(Department.objects.filter(name="Warehousing").exists())

    def test_apply_is_idempotent(self):
        self._call_command("--apply")
        counts = (Organization.objects.count(), Branch.objects.count(), Department.objects.count())
        output = self._call_command("--apply")

        self.assertEqual(counts, (Organization.objects.count(), Branch.objects.count(), Department.objects.count()))
        self.assertIn("created=0", output)
        self.assertIn("EXISTING", output)

    def test_membership_branch_population_only_when_single_branch_is_deterministic(self):
        au = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        png = Organization.objects.create(name="EFM PNG", slug="efm-png")
        role = self._role()
        au_user = CustomUser.objects.create_user(username="au-user")
        png_user = CustomUser.objects.create_user(username="png-user")
        au_membership = UserMembership.objects.create(user=au_user, organization=au, role=role)
        png_membership = UserMembership.objects.create(user=png_user, organization=png, role=role)

        output = self._call_command("--apply")
        au_membership.refresh_from_db()
        png_membership.refresh_from_db()

        self.assertEqual(au_membership.branch.name, "Brisbane")
        self.assertIsNone(png_membership.branch)
        self.assertIn("UPDATED: user_id=", output)
        self.assertIn("BLOCKED: user_id=", output)

    def test_legacy_test_org_is_not_deleted_or_modified(self):
        test_org = Organization.objects.create(name="Test Org", slug="test-org")

        self._call_command("--apply")
        test_org.refresh_from_db()

        self.assertEqual(test_org.name, "Test Org")
        self.assertTrue(Organization.objects.filter(pk=test_org.pk).exists())


class MembershipReassignmentPlanTests(TestCase):
    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_membership_reassignment_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="membership-plan-role"):
        return Role.objects.create(code=code, name=code.title(), is_system=True)

    def test_already_canonical_membership(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=org,
            code="AUS",
            name="EFM Australia",
            slug="efm-australia",
            country_code="AU",
        )
        branch = Branch.objects.create(organization=org, operating_entity=entity, code="BNE", name="Brisbane")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        user = CustomUser.objects.create_user(username="canonical-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "ALREADY_CANONICAL")
        self.assertEqual(row["suggested_organization"], "Express Freight Management")
        self.assertEqual(row["suggested_operating_entity"], "EFM Australia")
        self.assertEqual(row["suggested_branch"], "Brisbane")
        self.assertEqual(row["suggested_department"], "Air Freight")

    def test_legacy_organization_needs_manual_decision(self):
        legacy, _created = Organization.objects.get_or_create(
            name="EFM Express Air Cargo",
            defaults={"slug": "efm-express-air-cargo"},
        )
        department, _created = Department.objects.get_or_create(
            organization=legacy,
            code="AIR",
            defaults={"name": "Air Freight"},
        )
        user = CustomUser.objects.create_user(username="legacy-user")
        UserMembership.objects.create(user=user, organization=legacy, department=department, role=self._role())

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "NEEDS_MANUAL_DECISION")
        self.assertIsNone(row["suggested_organization"])
        self.assertIsNone(row["suggested_branch"])
        self.assertEqual(row["suggested_department"], "Air Freight")

    def test_missing_branch_on_single_branch_org_is_ready(self):
        org = Organization.objects.create(name="EFM Fiji", slug="efm-fiji")
        Branch.objects.create(organization=org, code="SUV", name="Suva")
        department = Department.objects.create(organization=org, code="CUS", name="Customs")
        user = CustomUser.objects.create_user(username="missing-branch-user")
        UserMembership.objects.create(user=user, organization=org, department=department, role=self._role())

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "READY")
        self.assertEqual(row["suggested_organization"], "Express Freight Management")
        self.assertEqual(row["suggested_operating_entity"], "EFM Fiji")
        self.assertEqual(row["suggested_branch"], "Suva")

    def test_missing_department_needs_manual_decision(self):
        org = Organization.objects.create(name="EFM Fiji", slug="efm-fiji")
        branch = Branch.objects.create(organization=org, code="SUV", name="Suva")
        user = CustomUser.objects.create_user(username="missing-department-user")
        UserMembership.objects.create(user=user, organization=org, branch=branch, role=self._role())

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "NEEDS_MANUAL_DECISION")
        self.assertIsNone(row["suggested_department"])

    def test_multi_branch_organization_blocks_missing_branch(self):
        org = Organization.objects.create(name="EFM PNG", slug="efm-png")
        Department.objects.create(organization=org, code="SEA", name="Sea Freight")
        user = CustomUser.objects.create_user(username="png-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            department=Department.objects.get(organization=org, code="SEA"),
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIsNone(row["suggested_branch"])

    def test_eac_department_maps_to_air_freight_only(self):
        org = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        Branch.objects.create(organization=org, code="BNE", name="Brisbane")
        eac_department = Department.objects.create(organization=org, code="EAC", name="EAC")
        user = CustomUser.objects.create_user(username="eac-dept-user")
        UserMembership.objects.create(user=user, organization=org, department=eac_department, role=self._role())

        payload = json.loads(self._call_report("--format", "json"))

        row = payload["memberships"][0]
        self.assertEqual(row["status"], "READY")
        self.assertEqual(row["suggested_department"], "Air Freight")
        self.assertNotEqual(row["suggested_department"], "EAC")

    def test_report_does_not_write(self):
        org = Organization.objects.create(name="EFM Fiji", slug="efm-fiji")
        Branch.objects.create(organization=org, code="SUV", name="Suva")
        department = Department.objects.create(organization=org, code="TRN", name="Transport")
        user = CustomUser.objects.create_user(username="readonly-user")
        membership = UserMembership.objects.create(user=user, organization=org, department=department, role=self._role())

        self._call_report()
        membership.refresh_from_db()

        self.assertIsNone(membership.branch)


class MembershipReassignmentCsvDraftTests(TestCase):
    def _call_draft(self, *args):
        stdout = StringIO()
        call_command("rbac_membership_reassignment_csv_draft", *args, stdout=stdout)
        return stdout.getvalue()

    def _rows(self, *args):
        return list(csv.DictReader(StringIO(self._call_draft(*args))))

    def _role(self, code="sales"):
        role, _created = Role.objects.get_or_create(
            code=code,
            organization=None,
            defaults={"name": code.title(), "is_system": True},
        )
        return role

    def _canonical_scope(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=org,
            code="AUS",
            name="EFM Australia",
            slug="efm-australia",
            country_code="AU",
        )
        branch = Branch.objects.create(organization=org, operating_entity=entity, code="BNE", name="Brisbane")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        return org, entity, branch, department

    def test_includes_legacy_memberships(self):
        legacy = Organization.objects.create(name="Legacy Org", slug="legacy-org")
        user = CustomUser.objects.create_user(username="legacy-draft-user")
        UserMembership.objects.create(user=user, organization=legacy, role=self._role())

        rows = self._rows()

        self.assertEqual(rows[0]["username"], "legacy-draft-user")
        self.assertEqual(rows[0]["current_organization"], "Legacy Org")
        self.assertIn("legacy/non-canonical membership", rows[0]["notes"])

    def test_includes_missing_branch_users(self):
        org, _entity, _branch, department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="missing-branch-draft-user")
        UserMembership.objects.create(user=user, organization=org, department=department, role=self._role())

        rows = self._rows()

        self.assertEqual(rows[0]["username"], "missing-branch-draft-user")
        self.assertIn("missing branch", rows[0]["notes"])

    def test_includes_missing_department_users(self):
        org, _entity, branch, _department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="missing-department-draft-user")
        UserMembership.objects.create(user=user, organization=org, branch=branch, role=self._role())

        rows = self._rows()

        self.assertEqual(rows[0]["username"], "missing-department-draft-user")
        self.assertIn("missing department", rows[0]["notes"])

    def test_includes_users_with_no_membership(self):
        CustomUser.objects.create_user(username="no-membership-draft-user")

        rows = self._rows()

        self.assertEqual(rows[0]["username"], "no-membership-draft-user")
        self.assertEqual(rows[0]["notes"], "no active membership")

    def test_target_fields_remain_blank_when_not_deterministic(self):
        org, _entity, _branch, department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="blank-target-draft-user")
        UserMembership.objects.create(user=user, organization=org, department=department, role=self._role())

        rows = self._rows()

        for field in ("target_organization", "target_operating_entity", "target_branch", "target_department", "target_role"):
            self.assertEqual(rows[0][field], "")

    def test_complete_canonical_membership_is_not_included(self):
        org, entity, branch, department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="complete-draft-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(),
        )

        rows = self._rows()

        self.assertEqual(rows, [])

    def test_proposes_operating_entity_from_branch(self):
        org, _entity, branch, department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="branch-entity-draft-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            branch=branch,
            department=department,
            role=self._role(),
        )

        rows = self._rows()

        self.assertEqual(rows[0]["current_operating_entity"], "")
        self.assertEqual(rows[0]["target_operating_entity"], "EFM Australia")
        self.assertIn("missing operating_entity", rows[0]["notes"])

    def test_output_option_writes_csv_file(self):
        CustomUser.objects.create_user(username="file-output-draft-user")
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        output = self._call_draft("--output", path)

        self.assertIn("Wrote 1 draft rows", output)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["username"], "file-output-draft-user")

    def test_no_writes_occur(self):
        org, _entity, _branch, department = self._canonical_scope()
        user = CustomUser.objects.create_user(username="no-write-draft-user")
        membership = UserMembership.objects.create(user=user, organization=org, department=department, role=self._role())

        self._call_draft()
        membership.refresh_from_db()

        self.assertIsNone(membership.branch)
        self.assertEqual(membership.department, department)


class ObsoleteUserCleanupPlanTests(TestCase):
    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_obsolete_user_cleanup_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="sales"):
        role, _created = Role.objects.get_or_create(
            code=code,
            organization=None,
            defaults={"name": code.title(), "is_system": True},
        )
        return role

    def _scope(self):
        org = Organization.objects.create(name="EFM PNG", slug="efm-png")
        branch = Branch.objects.create(organization=org, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        return org, branch, department

    def test_missing_users_are_reported_not_found(self):
        payload = json.loads(self._call_plan("--format", "json"))

        finance = next(row for row in payload["users"] if row["username"] == "finance")
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(finance["recommended_action"], "NOT_FOUND")
        self.assertEqual(finance["blocker_reason"], "user not found")

    def test_user_without_membership_or_dependencies_can_be_deactivated(self):
        CustomUser.objects.create_user(username="testuser")

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(row for row in payload["users"] if row["username"] == "testuser")
        self.assertEqual(row["recommended_action"], "DEACTIVATE_USER")
        self.assertFalse(row["has_active_membership"])

    def test_active_membership_is_planned_before_user_deactivation(self):
        org, branch, department = self._scope()
        user = CustomUser.objects.create_user(username="unassigned_user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            branch=branch,
            department=department,
            role=self._role(),
        )

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(row for row in payload["users"] if row["username"] == "unassigned_user")
        self.assertEqual(row["recommended_action"], "DEACTIVATE_MEMBERSHIP")
        self.assertTrue(row["has_active_membership"])
        self.assertEqual(row["current_organization"], "EFM PNG")
        self.assertEqual(row["branch"], "Port Moresby")
        self.assertEqual(row["department"], "Air Freight")

    def test_related_customer_dependency_blocks_cleanup(self):
        user = CustomUser.objects.create_user(username="finance")
        Company.objects.create(name="Owned Cleanup Customer", account_owner=user)

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(row for row in payload["users"] if row["username"] == "finance")
        self.assertEqual(row["recommended_action"], "REVIEW_DEPENDENCIES")
        self.assertEqual(row["dependency_counts"]["customer_account_owner"], 1)

    def test_text_output_summarizes_actions(self):
        CustomUser.objects.create_user(username="nas")

        output = self._call_plan()

        self.assertIn("RBAC obsolete user cleanup plan", output)
        self.assertIn("Mode: read-only diagnostics", output)
        self.assertIn("username=nas", output)
        self.assertIn("action=DEACTIVATE_USER", output)


class ObsoleteUserCleanupApplyTests(TestCase):
    def _call_apply(self, *args):
        stdout = StringIO()
        call_command("rbac_obsolete_user_cleanup_apply", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="sales"):
        role, _created = Role.objects.get_or_create(
            code=code,
            organization=None,
            defaults={"name": code.title(), "is_system": True},
        )
        return role

    def _scope(self):
        org = Organization.objects.create(name="EFM PNG", slug="efm-png-apply")
        branch = Branch.objects.create(organization=org, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        return org, branch, department

    def _membership(self, username="finance"):
        org, branch, department = self._scope()
        user = CustomUser.objects.create_user(username=username)
        membership = UserMembership.objects.create(
            user=user,
            organization=org,
            branch=branch,
            department=department,
            role=self._role(),
        )
        return user, membership

    def test_dry_run_no_writes(self):
        user, membership = self._membership("finance")

        payload = json.loads(self._call_apply("--format", "json"))

        user.refresh_from_db()
        membership.refresh_from_db()
        row = next(row for row in payload["users"] if row["username"] == "finance")
        self.assertEqual(payload["mode"], "dry-run")
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(row["status"], "PLANNED")
        self.assertTrue(user.is_active)
        self.assertTrue(membership.is_active)

    def test_active_membership_deactivation(self):
        user, membership = self._membership("nas")

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        user.refresh_from_db()
        membership.refresh_from_db()
        row = next(row for row in payload["users"] if row["username"] == "nas")
        self.assertEqual(row["status"], "APPLIED")
        self.assertEqual(row["action"], "DEACTIVATE_MEMBERSHIP")
        self.assertTrue(user.is_active)
        self.assertFalse(membership.is_active)

    def test_user_deactivation_when_no_active_membership(self):
        user = CustomUser.objects.create_user(username="system_user")

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        user.refresh_from_db()
        row = next(row for row in payload["users"] if row["username"] == "system_user")
        self.assertEqual(row["status"], "APPLIED")
        self.assertEqual(row["action"], "DEACTIVATE_USER")
        self.assertFalse(user.is_active)

    def test_dependency_blocker_skipped(self):
        user = CustomUser.objects.create_user(username="finance")
        Company.objects.create(name="Blocked Cleanup Customer", account_owner=user)

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        user.refresh_from_db()
        row = next(row for row in payload["users"] if row["username"] == "finance")
        self.assertEqual(row["status"], "BLOCKED_DEPENDENCIES")
        self.assertEqual(row["dependency_counts"]["customer_account_owner"], 1)
        self.assertTrue(user.is_active)

    def test_testuser_excluded(self):
        testuser = CustomUser.objects.create_user(username="testuser")

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        testuser.refresh_from_db()
        row = next(row for row in payload["users"] if row["username"] == "testuser")
        self.assertEqual(row["status"], "SKIPPED_DEPENDENCY_REVIEW_REQUIRED")
        self.assertTrue(testuser.is_active)

    def test_idempotent_second_apply_for_inactive_user(self):
        user = CustomUser.objects.create_user(username="unassigned_user")

        self._call_apply("--apply")
        self._call_apply("--apply")

        user.refresh_from_db()
        payload = json.loads(self._call_apply("--apply", "--format", "json"))
        row = next(row for row in payload["users"] if row["username"] == "unassigned_user")
        self.assertFalse(user.is_active)
        self.assertEqual(row["status"], "UNCHANGED")

    def test_json_output(self):
        payload = json.loads(self._call_apply("--format", "json"))

        self.assertEqual(payload["approved_targets"], ["finance", "nas", "system_user", "unassigned_user"])
        self.assertEqual(payload["excluded_targets"], ["testuser"])
        self.assertIn("planned_actions", payload)
        self.assertIn("applied_actions", payload)
        self.assertIn("skipped_users", payload)
        self.assertIn("dependency_blockers", payload)

    def test_no_crm_customer_quote_or_spot_writes(self):
        user = CustomUser.objects.create_user(username="finance")
        company = Company.objects.create(name="Untouched Cleanup Customer")
        opportunity = Opportunity.objects.create(
            company=company,
            title="Untouched Opportunity",
            service_type="AIR",
            owner=user,
        )
        task = Task.objects.create(
            company=company,
            description="Untouched task",
            owner=user,
            due_date=timezone.now().date(),
        )
        before = {
            "companies": Company.objects.count(),
            "opportunities": Opportunity.objects.count(),
            "tasks": Task.objects.count(),
            "quotes": Quote.objects.count(),
            "spot": SpotPricingEnvelopeDB.objects.count(),
            "company_owner": company.account_owner_id,
            "opportunity_owner": opportunity.owner_id,
            "task_owner": task.owner_id,
        }

        self._call_apply("--apply")

        company.refresh_from_db()
        opportunity.refresh_from_db()
        task.refresh_from_db()
        after = {
            "companies": Company.objects.count(),
            "opportunities": Opportunity.objects.count(),
            "tasks": Task.objects.count(),
            "quotes": Quote.objects.count(),
            "spot": SpotPricingEnvelopeDB.objects.count(),
            "company_owner": company.account_owner_id,
            "opportunity_owner": opportunity.owner_id,
            "task_owner": task.owner_id,
        }
        self.assertEqual(after, before)


class MembershipReassignmentTableValidateTests(TestCase):
    def _call_validate(self, rows, *args):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "username",
                    "target_organization",
                    "target_operating_entity",
                    "target_branch",
                    "target_department",
                    "target_role",
                    "approved",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        stdout = StringIO()
        call_command("rbac_membership_reassignment_table_validate", "--input", path, *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self):
        organization = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=organization,
            code="AUS",
            name="EFM Australia",
            slug="efm-australia",
            country_code="AU",
        )
        Branch.objects.create(organization=organization, operating_entity=entity, code="BNE", name="Brisbane")
        Department.objects.create(organization=organization, code="AIR", name="Air Freight")
        return organization

    def _role(self):
        role, _created = Role.objects.get_or_create(code="sales", defaults={"name": "Sales", "is_system": True})
        return role

    def _row(self, username="approved-user", **overrides):
        row = {
            "username": username,
            "target_organization": "Express Freight Management",
            "target_operating_entity": "EFM Australia",
            "target_branch": "Brisbane",
            "target_department": "Air Freight",
            "target_role": "sales",
            "approved": "yes",
            "notes": "approved",
        }
        row.update(overrides)
        return row

    def test_valid_approved_row_is_ready(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="approved-user")

        payload = json.loads(self._call_validate([self._row()], "--format", "json"))

        self.assertEqual(payload["summary"], {"blocked": 0, "ready": 1, "total": 1})
        self.assertEqual(payload["rows"][0]["status"], "READY")

    def test_missing_user_is_blocked(self):
        self._scope()
        self._role()

        payload = json.loads(self._call_validate([self._row(username="missing-user")], "--format", "json"))

        self.assertIn("user not found", payload["rows"][0]["errors"])

    def test_inactive_user_is_blocked(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="inactive-user", is_active=False)

        payload = json.loads(self._call_validate([self._row(username="inactive-user")], "--format", "json"))

        self.assertIn("user inactive", payload["rows"][0]["errors"])

    def test_non_canonical_organization_is_blocked(self):
        Organization.objects.create(name="EFM PNG", slug="efm-png")
        self._role()
        CustomUser.objects.create_user(username="legacy-org-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="legacy-org-user", target_organization="EFM PNG")],
                "--format",
                "json",
            )
        )

        self.assertIn("target organization is not canonical", payload["rows"][0]["errors"])

    def test_target_operating_entity_must_belong_to_target_organization(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="wrong-entity-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="wrong-entity-user", target_operating_entity="EFM PNG")],
                "--format",
                "json",
            )
        )

        self.assertIn("target operating_entity not found under target organization", payload["rows"][0]["errors"])

    def test_branch_must_belong_to_target_organization(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="wrong-branch-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="wrong-branch-user", target_branch="Port Moresby")],
                "--format",
                "json",
            )
        )

        self.assertIn("target branch not found under target organization", payload["rows"][0]["errors"])

    def test_non_canonical_department_is_blocked(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="warehouse-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="warehouse-user", target_department="Warehousing")],
                "--format",
                "json",
            )
        )

        self.assertIn("target department is not canonical", payload["rows"][0]["errors"])

    def test_eac_target_is_rejected(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="eac-target-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="eac-target-user", target_department="EAC")],
                "--format",
                "json",
            )
        )

        self.assertIn("EAC target value is not allowed", payload["rows"][0]["errors"])

    def test_duplicate_username_is_blocked(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="duplicate-user")

        payload = json.loads(
            self._call_validate(
                [self._row(username="duplicate-user"), self._row(username="duplicate-user")],
                "--format",
                "json",
            )
        )

        self.assertEqual(payload["summary"]["blocked"], 2)
        self.assertIn("duplicate username", payload["rows"][0]["errors"])
        self.assertIn("duplicate username", payload["rows"][1]["errors"])

    def test_unapproved_row_is_blocked(self):
        self._scope()
        self._role()
        CustomUser.objects.create_user(username="unapproved-user")

        payload = json.loads(
            self._call_validate([self._row(username="unapproved-user", approved="no")], "--format", "json")
        )

        self.assertIn("approved must be true or yes", payload["rows"][0]["errors"])

    def test_validation_does_not_write_memberships(self):
        self._scope()
        self._role()
        user = CustomUser.objects.create_user(username="no-write-user")

        self._call_validate([self._row(username="no-write-user")])

        self.assertFalse(UserMembership.objects.filter(user=user).exists())


class MembershipReassignmentApplyTests(TestCase):
    def _write_csv(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "username",
                    "target_organization",
                    "target_operating_entity",
                    "target_branch",
                    "target_department",
                    "target_role",
                    "approved",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _call_apply(self, rows, *args):
        stdout = StringIO()
        call_command("rbac_membership_reassignment_apply", "--input", self._write_csv(rows), *args, stdout=stdout)
        return stdout.getvalue()

    def _scope(self):
        organization = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=organization,
            code="AUS",
            name="EFM Australia",
            slug="efm-australia",
            country_code="AU",
        )
        branch = Branch.objects.create(organization=organization, operating_entity=entity, code="BNE", name="Brisbane")
        department = Department.objects.create(organization=organization, code="AIR", name="Air Freight")
        legacy_org = Organization.objects.create(name="Legacy Org", slug="legacy-org")
        legacy_department = Department.objects.create(organization=legacy_org, code="SEA", name="Sea Freight")
        role, _created = Role.objects.get_or_create(code="sales", defaults={"name": "Sales", "is_system": True})
        return organization, entity, branch, department, legacy_org, legacy_department, role

    def _row(self, username="apply-user", **overrides):
        row = {
            "username": username,
            "target_organization": "Express Freight Management",
            "target_operating_entity": "EFM Australia",
            "target_branch": "Brisbane",
            "target_department": "Air Freight",
            "target_role": "sales",
            "approved": "yes",
            "notes": "approved",
        }
        row.update(overrides)
        return row

    def _membership(self, username="apply-user"):
        _org, _entity, _branch, _dept, legacy_org, legacy_department, role = self._scope()
        user = CustomUser.objects.create_user(username=username)
        return UserMembership.objects.create(
            user=user,
            organization=legacy_org,
            department=legacy_department,
            role=role,
        )

    def test_dry_run_does_not_write(self):
        membership = self._membership()

        output = self._call_apply([self._row()])
        membership.refresh_from_db()

        self.assertIn("Mode: dry-run", output)
        self.assertIn("status=PLANNED", output)
        self.assertEqual(membership.organization.name, "Legacy Org")
        self.assertIsNone(membership.branch)

    def test_apply_updates_ready_membership(self):
        membership = self._membership()

        output = self._call_apply([self._row()], "--apply")
        membership.refresh_from_db()

        self.assertIn("status=APPLIED", output)
        self.assertEqual(membership.organization.name, "Express Freight Management")
        self.assertEqual(membership.operating_entity.name, "EFM Australia")
        self.assertEqual(membership.branch.name, "Brisbane")
        self.assertEqual(membership.department.name, "Air Freight")
        self.assertEqual(membership.role.code, "sales")

    def test_blocked_row_not_applied(self):
        membership = self._membership(username="blocked-user")

        output = self._call_apply([self._row(username="blocked-user", target_organization="EAC")], "--apply")
        membership.refresh_from_db()

        self.assertIn("status=BLOCKED", output)
        self.assertEqual(membership.organization.name, "Legacy Org")

    def test_duplicate_username_blocked(self):
        membership = self._membership(username="dupe-apply-user")

        output = self._call_apply(
            [self._row(username="dupe-apply-user"), self._row(username="dupe-apply-user")],
            "--apply",
        )
        membership.refresh_from_db()

        self.assertIn("blocked=2", output)
        self.assertEqual(membership.organization.name, "Legacy Org")

    def test_unapproved_row_blocked(self):
        membership = self._membership(username="unapproved-apply-user")

        output = self._call_apply([self._row(username="unapproved-apply-user", approved="no")], "--apply")
        membership.refresh_from_db()

        self.assertIn("approved must be true or yes", output)
        self.assertEqual(membership.organization.name, "Legacy Org")

    def test_missing_role_blocked(self):
        membership = self._membership(username="missing-role-apply-user")

        output = self._call_apply(
            [self._row(username="missing-role-apply-user", target_role="missing-role")],
            "--apply",
        )
        membership.refresh_from_db()

        self.assertIn("target role not found", output)
        self.assertEqual(membership.organization.name, "Legacy Org")

    def test_idempotent_second_apply(self):
        membership = self._membership(username="idempotent-user")

        self._call_apply([self._row(username="idempotent-user")], "--apply")
        output = self._call_apply([self._row(username="idempotent-user")], "--apply")
        membership.refresh_from_db()

        self.assertIn("unchanged=1", output)
        self.assertEqual(membership.organization.name, "Express Freight Management")
        self.assertEqual(membership.operating_entity.name, "EFM Australia")

    def test_previous_state_reported(self):
        self._membership(username="previous-state-user")

        payload = json.loads(self._call_apply([self._row(username="previous-state-user")], "--format", "json"))

        row = payload["rows"][0]
        self.assertEqual(row["previous"]["organization"], "Legacy Org")
        self.assertEqual(row["target"]["organization"], "Express Freight Management")
        self.assertEqual(row["target"]["operating_entity"], "EFM Australia")

    def test_no_customer_or_crm_writes_occur(self):
        membership = self._membership(username="no-customer-write-user")
        company = Company.objects.create(name="No Write Customer", organization=membership.organization)

        self._call_apply([self._row(username="no-customer-write-user")], "--apply")
        company.refresh_from_db()

        self.assertEqual(company.organization.name, "Legacy Org")


class PostMembershipApplyReadinessTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        OperatingEntity.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_report(self, *args):
        stdout = StringIO()
        call_command("rbac_post_membership_apply_readiness", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self):
        role, _created = Role.objects.get_or_create(
            code="sales",
            organization=None,
            defaults={"name": "Sales", "is_system": True},
        )
        return role

    def _canonical_master_data(self, *, skip_org=None, skip_branch=None, skip_department=None):
        branches = {
            "EFM PNG": ("Port Moresby", "Lae"),
            "EFM Australia": ("Brisbane",),
            "EFM Fiji": ("Suva",),
            "EFM Solomon Islands": ("Honiara",),
        }
        departments = ("Air Freight", "Sea Freight", "Customs", "Transport")
        organizations = {}
        if skip_org == "Express Freight Management":
            return organizations
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        organizations[org.name] = org
        for entity_name, branch_names in branches.items():
            entity = OperatingEntity.objects.create(
                organization=org,
                code=entity_name.split()[-1][:3].upper(),
                name=entity_name,
                slug=entity_name.lower().replace(" ", "-"),
                country_code=entity_name[:2].upper(),
            )
            for branch_name in branch_names:
                if (entity_name, branch_name) != skip_branch:
                    Branch.objects.create(
                        organization=org,
                        operating_entity=entity,
                        code=branch_name[:3].upper(),
                        name=branch_name,
                    )
        for department_name in departments:
            if ("Express Freight Management", department_name) != skip_department:
                Department.objects.create(organization=org, code=department_name[:3].upper(), name=department_name)
        return organizations

    def _complete_membership(self, username="ready-user", org_name="Express Freight Management"):
        org = Organization.objects.get(name=org_name)
        branch = Branch.objects.filter(organization=org).first()
        department = Department.objects.filter(organization=org, name="Air Freight").first()
        user = CustomUser.objects.create_user(username=username)
        return UserMembership.objects.create(
            user=user,
            organization=org,
            operating_entity=branch.operating_entity,
            branch=branch,
            department=department,
            role=self._role(),
        )

    def test_ready_state(self):
        self._canonical_master_data()
        self._complete_membership()

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["readiness"]["status"], "READY_FOR_BACKFILL_PLANNING")
        self.assertEqual(payload["memberships"]["complete_canonical_memberships"], 1)
        self.assertTrue(payload["canonical"]["organization_completeness"]["ready"])
        self.assertTrue(payload["canonical"]["operating_entity_completeness"]["ready"])

    def test_missing_canonical_org_blocks(self):
        self._canonical_master_data(skip_org="Express Freight Management")

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("Express Freight Management", payload["canonical"]["organizations_missing"])

    def test_missing_branch_blocks(self):
        self._canonical_master_data(skip_branch=("EFM Australia", "Brisbane"))
        self._complete_membership()

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("EFM Australia", payload["canonical"]["branches_missing"])

    def test_legacy_branch_does_not_satisfy_final_canonical_branch(self):
        self._canonical_master_data(skip_branch=("EFM Fiji", "Suva"))
        legacy = Organization.objects.create(name="EFM Fiji", slug="efm-fiji")
        Branch.objects.create(organization=legacy, code="SUV", name="Suva")
        self._complete_membership()

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("EFM Fiji", payload["canonical"]["branches_missing"])
        self.assertIn("Suva", payload["canonical"]["branches_missing"]["EFM Fiji"])

    def test_missing_department_blocks(self):
        self._canonical_master_data(skip_department=("Express Freight Management", "Air Freight"))
        self._complete_membership()

        payload = json.loads(self._call_report("--format", "json"))

        self.assertIn("Express Freight Management", payload["canonical"]["departments_missing"])

    def test_legacy_membership_blocks(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="Legacy Org", slug="legacy-org")
        user = CustomUser.objects.create_user(username="legacy-user")
        UserMembership.objects.create(user=user, organization=legacy, role=self._role())

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["legacy_non_canonical_organization_memberships"], 1)

    def test_missing_branch_membership_blocks(self):
        self._canonical_master_data()
        org = Organization.objects.get(name="Express Freight Management")
        entity = OperatingEntity.objects.get(organization=org, name="EFM Australia")
        user = CustomUser.objects.create_user(username="missing-branch-ready-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            operating_entity=entity,
            department=Department.objects.get(organization=org, name="Air Freight"),
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["missing_branch"], 1)

    def test_missing_department_membership_blocks(self):
        self._canonical_master_data()
        org = Organization.objects.get(name="Express Freight Management")
        branch = Branch.objects.filter(organization=org).first()
        user = CustomUser.objects.create_user(username="missing-dept-ready-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            operating_entity=branch.operating_entity,
            branch=branch,
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["missing_department"], 1)

    def test_missing_operating_entity_membership_reported(self):
        self._canonical_master_data()
        org = Organization.objects.get(name="Express Freight Management")
        user = CustomUser.objects.create_user(username="missing-entity-ready-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            branch=Branch.objects.filter(organization=org).first(),
            department=Department.objects.get(organization=org, name="Air Freight"),
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["memberships_missing_operating_entity"], 1)
        self.assertEqual(payload["memberships"]["memberships_inferable_from_branch"], 1)
        self.assertEqual(payload["memberships"]["memberships_not_inferable"], 0)
        self.assertTrue(payload["memberships"]["scope_resolution_operating_entity_ready"])
        self.assertTrue(payload["memberships"]["membership_operating_entity_completeness"]["ready"])
        self.assertEqual(payload["memberships"]["missing_operating_entity"], 1)
        self.assertEqual(payload["memberships"]["active_memberships_by_status"]["operating_entity_inferable_from_branch"], 1)

    def test_missing_operating_entity_without_branch_link_reported_not_inferable(self):
        self._canonical_master_data()
        org = Organization.objects.get(name="Express Freight Management")
        branch = Branch.objects.create(organization=org, code="LEG", name="Legacy Branch")
        user = CustomUser.objects.create_user(username="not-inferable-entity-ready-user")
        UserMembership.objects.create(
            user=user,
            organization=org,
            branch=branch,
            department=Department.objects.get(organization=org, name="Air Freight"),
            role=self._role(),
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["memberships_missing_operating_entity"], 1)
        self.assertEqual(payload["memberships"]["memberships_inferable_from_branch"], 0)
        self.assertEqual(payload["memberships"]["memberships_not_inferable"], 1)
        self.assertFalse(payload["memberships"]["scope_resolution_operating_entity_ready"])
        self.assertFalse(payload["memberships"]["membership_operating_entity_completeness"]["ready"])
        self.assertFalse(payload["canonical"]["branch_operating_entity_completeness"]["ready"])
        self.assertEqual(payload["final_readiness"]["status"], "NOT_READY")
        self.assertTrue(any("memberships_not_inferable" in blocker for blocker in payload["final_readiness"]["blockers"]))

    def test_final_readiness_command_is_read_only(self):
        self._canonical_master_data()
        membership = self._complete_membership()
        before = (Organization.objects.count(), Branch.objects.count(), UserMembership.objects.count())

        payload = json.loads(self._call_report("--format", "json"))

        membership.refresh_from_db()
        self.assertFalse(payload["write_enabled"])
        self.assertEqual((Organization.objects.count(), Branch.objects.count(), UserMembership.objects.count()), before)
        self.assertTrue(membership.is_active)

    def test_final_readiness_detects_missing_operating_entity_links(self):
        self._canonical_master_data()
        branch = Branch.objects.get(name="Port Moresby")
        branch.operating_entity = None
        branch.save(update_fields=["operating_entity"])

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["canonical"]["branch_operating_entity_completeness"]["missing_operating_entity"], 1)
        self.assertFalse(payload["canonical"]["branch_operating_entity_completeness"]["ready"])
        self.assertEqual(payload["final_readiness"]["status"], "NOT_READY")

    def test_final_readiness_reports_legacy_organization_dependencies(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        Company.objects.create(name="Legacy EAC Customer", organization=legacy)

        payload = json.loads(self._call_report("--format", "json"))

        eac = payload["legacy"]["eac_legacy_references"]
        self.assertEqual(eac["organization_names"], ["EFM Express Air Cargo"])
        self.assertGreaterEqual(eac["dependency_count"], 1)
        self.assertEqual(payload["final_readiness"]["status"], "NOT_READY")

    def test_inactive_legacy_organization_dependencies_do_not_block_final_readiness(self):
        self._canonical_master_data()
        self._complete_membership()
        legacy = Organization.objects.create(name="EFM Australia", slug="efm-australia", is_active=False)
        Company.objects.create(name="Inactive Legacy AU Customer", organization=legacy)

        payload = json.loads(self._call_report("--format", "json"))

        country = payload["legacy"]["country_as_organization_dependencies"]
        self.assertEqual(country["active_dependency_count"], 0)
        self.assertTrue(country["inactive_or_dependency_free"])
        self.assertFalse(
            any("active_legacy_country_as_organization_dependencies" in blocker for blocker in payload["final_readiness"]["blockers"])
        )

    def test_final_readiness_reports_superseded_stale_artifacts(self):
        payload = json.loads(self._call_report("--format", "json"))

        self.assertTrue(payload["stale_artifacts"])
        self.assertTrue(all(row["status"] == "superseded_legacy_reference" for row in payload["stale_artifacts"]))
        self.assertTrue(
            any("Quote/SPOT historical records remain DEV_TEST_LEGACY" in note for note in payload["final_readiness"]["notes"])
        )

    def test_active_user_with_no_membership_blocks(self):
        self._canonical_master_data()
        CustomUser.objects.create_user(username="no-membership-user")

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["users_with_no_active_membership"], 1)

    def test_multiple_active_memberships_block(self):
        self._canonical_master_data()
        membership = self._complete_membership()
        UserMembership.objects.create(
            user=membership.user,
            organization=membership.organization,
            operating_entity=membership.operating_entity,
            branch=membership.branch,
            department=membership.department,
            role=membership.role,
            is_primary=False,
        )

        payload = json.loads(self._call_report("--format", "json"))

        self.assertEqual(payload["memberships"]["users_with_multiple_active_memberships"], 1)

    def test_json_output_contains_write_disabled(self):
        self._canonical_master_data()
        self._complete_membership()

        payload = json.loads(self._call_report("--format", "json"))

        self.assertFalse(payload["write_enabled"])

    def test_report_does_not_write(self):
        self._canonical_master_data()
        membership = self._complete_membership()

        self._call_report()
        membership.refresh_from_db()

        self.assertEqual(membership.organization.name, "Express Freight Management")


class OrganizationModelRedesignAuditTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        OperatingEntity.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_audit(self, *args):
        stdout = StringIO()
        call_command("rbac_organization_model_redesign_audit", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self):
        return Role.objects.create(code="admin", name="Admin", is_system=True)

    def _fixtures(self):
        parent = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        png = Organization.objects.create(name="EFM PNG", slug="efm-png")
        au = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        eac = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        test_org = Organization.objects.create(name="Test Org", slug="test-org")

        png_pom = Branch.objects.create(organization=png, code="POM", name="Port Moresby")
        au_pom = Branch.objects.create(organization=au, code="POM", name="Port Moresby")
        png_air = Department.objects.create(organization=png, branch=png_pom, code="AIR", name="Air Freight")
        au_air = Department.objects.create(organization=au, branch=au_pom, code="AIR", name="Air Freight")

        user = CustomUser.objects.create_user(username="phase10a-user")
        membership = UserMembership.objects.create(
            user=user,
            organization=eac,
            branch=png_pom,
            department=png_air,
            role=self._role(),
        )
        company = Company.objects.create(name="Phase 10A Customer", organization=png, branch=png_pom, department=png_air)
        Contact.objects.create(
            company=company,
            first_name="Phase",
            last_name="Contact",
            email="phase10a@example.com",
            organization=png,
            branch=png_pom,
            department=png_air,
        )
        Opportunity.objects.create(
            company=company,
            title="Phase 10A Opportunity",
            service_type="AIR",
            organization=png,
            branch=png_pom,
            department=png_air,
        )
        Quote.objects.create(customer=company, organization=png, branch=png_pom, department=png_air)
        SpotPricingEnvelopeDB.objects.create(
            organization=png,
            branch=png_pom,
            department=png_air,
            shipment_context_json={"origin": "POM", "destination": "BNE"},
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test trigger",
            expires_at=timezone.now(),
        )
        return {
            "parent": parent,
            "png": png,
            "au": au,
            "eac": eac,
            "test_org": test_org,
            "membership": membership,
            "company": company,
            "png_air": png_air,
            "au_air": au_air,
        }

    def test_json_reports_corrected_business_rule_and_target_model(self):
        self._fixtures()

        payload = json.loads(self._call_audit("--format", "json"))

        self.assertFalse(payload["write_enabled"])
        self.assertIn("Express Freight Management is the only organization", payload["business_rule"])
        self.assertEqual(
            payload["recommended_target_model"]["selected"],
            "Option B: add OperatingEntity between Organization and Branch",
        )
        self.assertEqual(payload["current_counts"]["organizations"], 5)

    def test_detects_multiple_organizations_and_legacy_eac(self):
        self._fixtures()

        payload = json.loads(self._call_audit("--format", "json"))

        classifications = {row["name"]: row["classification"] for row in payload["organizations"]}
        self.assertEqual(classifications["Express Freight Management"], "canonical keep")
        self.assertEqual(classifications["EFM PNG"], "migrate/reparent")
        self.assertEqual(classifications["EFM Australia"], "migrate/reparent")
        self.assertEqual(classifications["EFM Express Air Cargo"], "archive/deactivate")
        self.assertEqual(classifications["Test Org"], "archive/deactivate")

    def test_detects_duplicated_branches_and_departments_under_legacy_orgs(self):
        self._fixtures()

        payload = json.loads(self._call_audit("--format", "json"))

        branch_names = {row["name"] for row in payload["duplicate_risks"]["duplicated_branches_under_legacy_organizations"]}
        department_names = {row["name"] for row in payload["duplicate_risks"]["duplicated_departments_under_legacy_organizations"]}
        self.assertIn("port moresby", branch_names)
        self.assertIn("air freight", department_names)

    def test_reports_memberships_and_scoped_record_dependencies(self):
        self._fixtures()

        payload = json.loads(self._call_audit("--format", "json"))

        self.assertEqual(payload["memberships"]["count"], 1)
        self.assertGreater(payload["scoped_records"]["parties.Company"]["with_organization"], 0)
        self.assertGreater(payload["scoped_records"]["crm.Opportunity"]["with_organization"], 0)
        self.assertGreater(payload["quote_spot_productcode"]["quotes"]["with_organization"], 0)
        self.assertGreater(payload["quote_spot_productcode"]["spot_envelopes"]["with_organization"], 0)
        self.assertTrue(
            any(row["model"] == "accounts.UserMembership" and row["field"] == "organization" for row in payload["fk_dependencies"])
        )

    def test_command_is_read_only(self):
        fixtures = self._fixtures()
        before = fixtures["membership"].organization_id

        self._call_audit()

        fixtures["membership"].refresh_from_db()
        self.assertEqual(fixtures["membership"].organization_id, before)


class HierarchyToolingAlignmentAuditTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_audit(self, *args):
        stdout = StringIO()
        call_command("rbac_hierarchy_tooling_alignment_audit", *args, stdout=stdout)
        return stdout.getvalue()

    def test_reports_stale_country_as_organization_tooling(self):
        Organization.objects.create(name="Express Freight Management", slug="efm")
        Organization.objects.create(name="EFM PNG", slug="efm-png")
        Organization.objects.create(name="EFM Australia", slug="efm-australia")
        Organization.objects.create(name="EFM Fiji", slug="efm-fiji")
        Organization.objects.create(name="EFM Solomon Islands", slug="efm-solomon-islands")
        Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")

        payload = json.loads(self._call_audit("--format", "json"))

        self.assertFalse(payload["write_enabled"])
        self.assertEqual(payload["corrected_hierarchy"]["organization"], "Express Freight Management")
        self.assertIn("requires OperatingEntity model", payload["summary"])
        self.assertIn("requires migration phase", payload["summary"])
        self.assertIn("safe to update now", payload["summary"])
        self.assertIn("should be retired", payload["summary"])
        self.assertEqual(
            payload["current_master_data"]["organizations"]["country_entities_still_stored_as_organizations"],
            ["EFM Australia", "EFM Fiji", "EFM PNG", "EFM Solomon Islands"],
        )
        self.assertTrue(payload["current_master_data"]["organizations"]["legacy_eac_organization_exists"])

    def test_identifies_outdated_readiness_command_assumption(self):
        payload = json.loads(self._call_audit("--format", "json"))

        row = next(
            item
            for item in payload["stale_assumptions"]
            if item["path"].endswith("rbac_post_membership_apply_readiness.py")
        )
        self.assertTrue(row["mentions_country_as_organization"])
        self.assertEqual(row["classification"], "requires OperatingEntity model")

    def test_identifies_legacy_eac_docs_to_retire(self):
        payload = json.loads(self._call_audit("--format", "json"))

        retired = [
            row for row in payload["stale_assumptions"]
            if row["classification"] == "should be retired"
        ]
        self.assertTrue(any(row["mentions_legacy_eac"] for row in retired))

    def test_command_is_read_only(self):
        org = Organization.objects.create(name="EFM PNG", slug="efm-png")

        self._call_audit()

        org.refresh_from_db()
        self.assertEqual(org.name, "EFM PNG")
        self.assertTrue(org.is_active)

    def test_classifies_quote_spot_scoped_records_as_dev_test_legacy(self):
        org = Organization.objects.create(name="EFM PNG", slug="efm-png")
        branch = Branch.objects.create(organization=org, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=org, branch=branch, code="AIR", name="Air Freight")
        customer = Company.objects.create(name="Dev Quote Customer", organization=org, branch=branch, department=department)
        Quote.objects.create(customer=customer, mode="AIR", organization=org, branch=branch, department=department)
        SpotPricingEnvelopeDB.objects.create(
            organization=org,
            branch=branch,
            department=department,
            shipment_context_json={"origin": "POM"},
            expires_at=timezone.now(),
        )

        payload = json.loads(self._call_audit("--format", "json"))
        quote_spot = payload["quote_spot_scope"]

        self.assertEqual(quote_spot["classification"], "DEV_TEST_LEGACY")
        self.assertFalse(quote_spot["historical_backfill_required"])
        self.assertFalse(quote_spot["build_historical_backfill_tooling"])
        self.assertEqual(quote_spot["quote"]["classification_by_record_policy"], {"DEV_TEST_LEGACY": 1})
        self.assertEqual(quote_spot["spot"]["classification_by_record_policy"], {"DEV_TEST_LEGACY": 1})
        self.assertEqual(quote_spot["separation_rule"], "CRM/customer/user membership hierarchy work remains separate.")

    def test_reports_future_quote_spot_scope_expectation_without_enforcement(self):
        payload = json.loads(self._call_audit("--format", "json"))
        future_scope = payload["quote_spot_scope"]["future_scope_expectation"]

        self.assertEqual(future_scope["status"], "FUTURE_SCOPE_DIAGNOSTIC_ONLY")
        self.assertTrue(future_scope["quote_save_uses_resolve_create_scope_for_user"])
        self.assertTrue(future_scope["spot_save_uses_resolve_create_scope_for_user"])


class OperatingEntityModelDesignTests(TestCase):
    def _call_design(self, *args):
        stdout = StringIO()
        call_command("rbac_operating_entity_model_design", *args, stdout=stdout)
        return stdout.getvalue()

    def test_json_defines_operating_entity_design(self):
        payload = json.loads(self._call_design("--format", "json"))

        self.assertFalse(payload["write_enabled"])
        self.assertEqual(payload["target_hierarchy"]["organization"], "Express Freight Management")
        self.assertEqual(payload["proposed_model"]["name"], "OperatingEntity")
        self.assertIn("UniqueConstraint(fields=['organization', 'code'])", payload["proposed_model"]["constraints"])
        self.assertIn("add OperatingEntity model only; no data migration or enforcement", payload["migration_order"])

    def test_classifies_current_scope_references(self):
        payload = json.loads(self._call_design("--format", "json"))
        references = {row["model"]: row for row in payload["current_scope_references"]}

        self.assertEqual(references["parties.Branch"]["operating_entity_need"], "needs_operating_entity_later")
        self.assertEqual(references["accounts.UserMembership"]["operating_entity_need"], "needs_operating_entity_later")
        self.assertEqual(references["parties.OrganizationBranding"]["operating_entity_need"], "review_branding_model_separately")

    def test_command_is_read_only(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")

        self._call_design()

        org.refresh_from_db()
        self.assertEqual(org.name, "Express Freight Management")
        self.assertTrue(org.is_active)


class OperatingEntitySchemaTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Express Freight Management",
            slug="express-freight-management",
        )

    def test_model_creation_and_organization_relationship(self):
        entity = OperatingEntity.objects.create(
            organization=self.organization,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )

        self.assertEqual(entity.organization, self.organization)
        self.assertEqual(list(self.organization.operating_entities.all()), [entity])
        self.assertEqual(str(entity), "express-freight-management:PNG")
        self.assertTrue(entity.is_active)

    def test_branch_can_link_to_operating_entity(self):
        entity = OperatingEntity.objects.create(
            organization=self.organization,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        branch = Branch.objects.create(
            organization=self.organization,
            operating_entity=entity,
            code="POM",
            name="Port Moresby",
        )

        self.assertEqual(branch.operating_entity, entity)
        self.assertEqual(list(entity.branches.all()), [branch])

    def test_unique_constraints_are_per_organization(self):
        OperatingEntity.objects.create(
            organization=self.organization,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )

        duplicate_cases = [
            {"code": "PNG", "name": "EFM Australia", "slug": "efm-australia", "country_code": "AU"},
            {"code": "AU", "name": "EFM PNG", "slug": "efm-australia", "country_code": "AU"},
            {"code": "AU", "name": "EFM Australia", "slug": "efm-png", "country_code": "AU"},
        ]
        for values in duplicate_cases:
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        OperatingEntity.objects.create(organization=self.organization, **values)

    def test_migration_exists_without_data_operation(self):
        migration_path = Path(__file__).resolve().parent / "migrations" / "0010_operatingentity.py"

        self.assertTrue(migration_path.exists())
        migration_text = migration_path.read_text(encoding="utf-8")
        self.assertNotIn("RunPython", migration_text)
        self.assertNotIn("RunSQL", migration_text)


class OperatingEntitySeedCommandTests(TestCase):
    def _call(self, command, *args):
        stdout = StringIO()
        call_command(command, *args, stdout=stdout)
        return stdout.getvalue()

    def test_seed_command_creates_canonical_entities(self):
        output = self._call("seed_operating_entities")

        organization = Organization.objects.get(name="Express Freight Management")
        self.assertEqual(organization.operating_entities.count(), 4)
        self.assertTrue(OperatingEntity.objects.filter(organization=organization, name="EFM PNG", code="PNG").exists())
        self.assertIn("created=4", output)

    def test_seed_command_is_idempotent(self):
        self._call("seed_operating_entities")
        output = self._call("seed_operating_entities")

        self.assertEqual(OperatingEntity.objects.count(), 4)
        self.assertIn("existing=4", output)

    def test_link_command_associates_canonical_branches(self):
        self._call("seed_operating_entities")
        organization = Organization.objects.get(name="Express Freight Management")
        for code, name in (("POM", "Port Moresby"), ("LAE", "Lae"), ("BNE", "Brisbane"), ("SUV", "Suva"), ("HIR", "Honiara")):
            Branch.objects.create(organization=organization, code=code, name=name)

        output = self._call("link_branch_operating_entities")

        self.assertEqual(Branch.objects.filter(operating_entity__isnull=False).count(), 5)
        self.assertEqual(Branch.objects.get(name="Port Moresby").operating_entity.name, "EFM PNG")
        self.assertIn("linked=5", output)

    def test_link_command_is_idempotent(self):
        self._call("seed_operating_entities")
        organization = Organization.objects.get(name="Express Freight Management")
        for code, name in (("POM", "Port Moresby"), ("LAE", "Lae"), ("BNE", "Brisbane"), ("SUV", "Suva"), ("HIR", "Honiara")):
            Branch.objects.create(organization=organization, code=code, name=name)

        self._call("link_branch_operating_entities")
        output = self._call("link_branch_operating_entities")

        self.assertIn("existing=5", output)

    def test_final_hierarchy_seed_creates_missing_branches_and_departments(self):
        self._call("seed_operating_entities")

        output = self._call("seed_final_rbac_hierarchy")

        organization = Organization.objects.get(name="Express Freight Management")
        self.assertEqual(Branch.objects.filter(organization=organization).count(), 5)
        self.assertEqual(Department.objects.filter(organization=organization).count(), 4)
        self.assertEqual(Branch.objects.get(organization=organization, name="Suva").operating_entity.name, "EFM Fiji")
        self.assertIn("created=9", output)

    def test_final_hierarchy_seed_is_idempotent(self):
        self._call("seed_operating_entities")
        self._call("seed_final_rbac_hierarchy")
        output = self._call("seed_final_rbac_hierarchy")

        self.assertEqual(Branch.objects.count(), 5)
        self.assertEqual(Department.objects.count(), 4)
        self.assertIn("existing=9", output)

    def test_final_hierarchy_seed_dry_run_writes_nothing(self):
        self._call("seed_operating_entities")

        output = self._call("seed_final_rbac_hierarchy", "--dry-run")

        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(Department.objects.count(), 0)
        self.assertIn("created=9", output)

    def test_final_hierarchy_seed_deactivates_dependency_free_extra_branch(self):
        self._call("seed_operating_entities")
        organization = Organization.objects.get(name="Express Freight Management")
        extra = Branch.objects.create(organization=organization, code="FIJ", name="Fiji")

        output = self._call("seed_final_rbac_hierarchy")

        extra.refresh_from_db()
        self.assertFalse(extra.is_active)
        self.assertIn("deactivated=1", output)


class FinalUserBlockerResolutionPlanTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_final_user_blocker_resolution_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="admin"):
        role, _created = Role.objects.get_or_create(
            code=code,
            organization=None,
            defaults={"name": code.title(), "is_system": True},
        )
        return role

    def _canonical_scope(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=org,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        branch = Branch.objects.create(organization=org, operating_entity=entity, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        return org, entity, branch, department

    def _spot_envelope(self, user, *, owner=None):
        return SpotPricingEnvelopeDB.objects.create(
            created_by=user,
            owner=owner,
            shipment_context_json={"origin": "POM", "destination": "LAE"},
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test trigger",
            expires_at=timezone.now(),
        )

    def test_reports_testuser_spot_created_by_dependencies(self):
        org, entity, branch, department = self._canonical_scope()
        testuser = CustomUser.objects.create_user(username="testuser", email="test@example.com")
        owner = CustomUser.objects.create_user(username="admin", role=CustomUser.ROLE_ADMIN)
        UserMembership.objects.create(
            user=owner,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(),
        )
        self._spot_envelope(testuser, owner=owner)
        self._spot_envelope(testuser)

        payload = json.loads(self._call_plan("--format", "json"))

        row = payload["active_users_with_no_membership"][0]
        self.assertEqual(row["username"], "testuser")
        self.assertEqual(row["dependency_counts"]["spot_envelope_created_by"], 2)
        self.assertEqual(row["spot_envelope_created_by_count"], 2)
        self.assertEqual(row["spot_envelope_owner_count"], 2)
        self.assertEqual(row["spot_envelope_missing_owner_count"], 0)
        self.assertEqual(row["recommended_action"], "REVIEW_SPOT_CREATED_BY_REASSIGNMENT")

    def test_reports_sysadmin_candidate_membership(self):
        legacy = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        sysadmin = CustomUser.objects.create_user(username="sysadmin", role=CustomUser.ROLE_ADMIN)
        UserMembership.objects.create(user=sysadmin, organization=legacy, role=self._role())

        payload = json.loads(self._call_plan("--format", "json"))

        row = payload["legacy_non_canonical_active_memberships"][0]
        self.assertEqual(row["username"], "sysadmin")
        self.assertEqual(row["current_membership"]["organization"], "EFM Express Air Cargo")
        self.assertEqual(row["current_membership"]["branch"], "")
        self.assertEqual(row["current_membership"]["department"], "")
        self.assertEqual(
            row["candidate_canonical_membership"],
            {
                "organization": "Express Freight Management",
                "operating_entity": "EFM PNG",
                "branch": "Port Moresby",
                "department": "Air Freight",
                "role": "admin",
            },
        )
        self.assertEqual(row["recommended_action"], "READY_FOR_MEMBERSHIP_REASSIGNMENT")

    def test_candidate_reassignment_users_are_complete_canonical_admins(self):
        org, entity, branch, department = self._canonical_scope()
        admin = CustomUser.objects.create_user(username="approved-admin", role=CustomUser.ROLE_ADMIN)
        sales = CustomUser.objects.create_user(username="sales-user", role=CustomUser.ROLE_SALES)
        testuser = CustomUser.objects.create_user(username="testuser")
        UserMembership.objects.create(
            user=admin,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(),
        )
        UserMembership.objects.create(
            user=sales,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(CustomUser.ROLE_SALES),
        )
        self._spot_envelope(testuser)

        payload = json.loads(self._call_plan("--format", "json"))

        row = payload["active_users_with_no_membership"][0]
        self.assertEqual([candidate["username"] for candidate in row["candidate_reassignment_users"]], ["approved-admin"])

    def test_json_output_and_text_output(self):
        CustomUser.objects.create_user(username="testuser")

        payload = json.loads(self._call_plan("--format", "json"))
        output = self._call_plan()

        self.assertFalse(payload["write_enabled"])
        self.assertIn("RBAC final user blocker resolution plan", output)
        self.assertIn("username=testuser", output)

    def test_report_does_not_write(self):
        legacy = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        sysadmin = CustomUser.objects.create_user(username="sysadmin", role=CustomUser.ROLE_ADMIN)
        membership = UserMembership.objects.create(user=sysadmin, organization=legacy, role=self._role())

        self._call_plan()

        membership.refresh_from_db()
        sysadmin.refresh_from_db()
        self.assertTrue(sysadmin.is_active)
        self.assertEqual(membership.organization.name, "EFM Express Air Cargo")
        self.assertTrue(membership.is_active)


class FinalUserBlockerResolutionApplyTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        OperatingEntity.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_apply(self, *args):
        stdout = StringIO()
        call_command("rbac_final_user_blocker_resolution_apply", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self, code="admin"):
        role, _created = Role.objects.get_or_create(
            code=code,
            organization=None,
            defaults={"name": code.title(), "is_system": True},
        )
        return role

    def _canonical_master_data(self):
        specs = {
            "EFM PNG": ("Port Moresby", "Lae"),
            "EFM Australia": ("Brisbane",),
            "EFM Fiji": ("Suva",),
            "EFM Solomon Islands": ("Honiara",),
        }
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        for entity_name, branches in specs.items():
            entity = OperatingEntity.objects.create(
                organization=org,
                code=entity_name.split()[-1][:3].upper(),
                name=entity_name,
                slug=entity_name.lower().replace(" ", "-"),
                country_code=entity_name[:2].upper(),
            )
            for branch_name in branches:
                Branch.objects.create(
                    organization=org,
                    operating_entity=entity,
                    code=branch_name[:3].upper(),
                    name=branch_name,
                )
        for department_name in ("Air Freight", "Sea Freight", "Customs", "Transport"):
            Department.objects.create(organization=org, code=department_name[:3].upper(), name=department_name)

    def _canonical_scope(self):
        org = Organization.objects.get(name="Express Freight Management")
        entity = OperatingEntity.objects.get(organization=org, name="EFM PNG")
        return (
            org,
            entity,
            Branch.objects.get(organization=org, name="Port Moresby"),
            Department.objects.get(organization=org, name="Air Freight"),
        )

    def _fixtures(self, *, with_customer_dependency=False):
        self._canonical_master_data()
        org, entity, branch, department = self._canonical_scope()
        admin = CustomUser.objects.create_user(
            username="nason.martin",
            email="nason.martin@efmpng.com",
            role=CustomUser.ROLE_ADMIN,
        )
        UserMembership.objects.create(
            user=admin,
            organization=org,
            operating_entity=entity,
            branch=branch,
            department=department,
            role=self._role(),
        )
        testuser = CustomUser.objects.create_user(username="testuser", email="test@example.com")
        for _index in range(2):
            envelope = SpotPricingEnvelopeDB.objects.create(
                created_by=testuser,
                owner=admin,
                shipment_context_json={"origin": "POM", "destination": "LAE"},
                conditions_json={},
                spot_trigger_reason_code="TEST",
                spot_trigger_reason_text="Test trigger",
                expires_at=timezone.now(),
            )
            envelope.owner = admin
            envelope.save(update_fields=["owner"])
        if with_customer_dependency:
            Company.objects.create(name="Testuser Customer", account_owner=testuser)
        legacy = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        sysadmin = CustomUser.objects.create_user(username="sysadmin", role=CustomUser.ROLE_ADMIN)
        legacy_membership = UserMembership.objects.create(user=sysadmin, organization=legacy, role=self._role())
        return admin, testuser, sysadmin, legacy_membership

    def test_dry_run_does_not_write(self):
        _admin, testuser, _sysadmin, legacy_membership = self._fixtures()

        payload = json.loads(self._call_apply("--format", "json"))

        testuser.refresh_from_db()
        legacy_membership.refresh_from_db()
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["summary"]["planned"], 2)
        self.assertTrue(testuser.is_active)
        self.assertTrue(SpotPricingEnvelopeDB.objects.filter(created_by=testuser).exists())
        self.assertTrue(legacy_membership.is_active)

    def test_apply_reassigns_spot_created_by_and_deactivates_testuser(self):
        admin, testuser, _sysadmin, _legacy_membership = self._fixtures()

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        testuser.refresh_from_db()
        self.assertEqual(payload["summary"]["applied"], 2)
        self.assertFalse(SpotPricingEnvelopeDB.objects.filter(created_by=testuser).exists())
        self.assertEqual(SpotPricingEnvelopeDB.objects.filter(created_by=admin).count(), 2)
        self.assertFalse(testuser.is_active)

    def test_apply_refuses_testuser_deactivation_if_dependencies_remain(self):
        _admin, testuser, sysadmin, legacy_membership = self._fixtures(with_customer_dependency=True)

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        testuser.refresh_from_db()
        legacy_membership.refresh_from_db()
        self.assertEqual(payload["summary"]["blocked"], 1)
        self.assertEqual(payload["summary"]["applied"], 0)
        self.assertNotIn("APPLIED", {row["status"] for row in payload["actions"]})
        self.assertTrue(testuser.is_active)
        self.assertEqual(SpotPricingEnvelopeDB.objects.filter(created_by=testuser).count(), 2)
        self.assertTrue(legacy_membership.is_active)
        self.assertEqual(
            list(UserMembership.objects.filter(user=sysadmin, is_active=True).values_list("organization__name", flat=True)),
            ["EFM Express Air Cargo"],
        )

    def test_apply_deactivates_zero_dependency_user_with_no_membership(self):
        self._fixtures()
        orphan = CustomUser.objects.create_user(username="orphan-zero-dependency", email="orphan@example.com")

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        orphan.refresh_from_db()
        self.assertFalse(orphan.is_active)
        self.assertTrue(
            any(
                row["username"] == "orphan-zero-dependency"
                and row["action"] == "DEACTIVATE_ZERO_DEPENDENCY_USER_WITH_NO_MEMBERSHIP"
                for row in payload["actions"]
            )
        )

    def test_apply_moves_sysadmin_to_canonical_membership(self):
        _admin, _testuser, sysadmin, legacy_membership = self._fixtures()

        self._call_apply("--apply")

        legacy_membership.refresh_from_db()
        active = UserMembership.objects.select_related("organization", "operating_entity", "branch", "department", "role").get(
            user=sysadmin,
            is_active=True,
        )
        self.assertFalse(legacy_membership.is_active)
        self.assertEqual(active.organization.name, "Express Freight Management")
        self.assertIsNone(active.operating_entity)
        self.assertEqual(active.branch.name, "Port Moresby")
        self.assertEqual(active.department.name, "Air Freight")
        self.assertEqual(active.role.code, "admin")

    def test_apply_is_idempotent(self):
        self._fixtures()

        self._call_apply("--apply")
        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        self.assertEqual(payload["summary"]["unchanged"], 2)

    def test_json_output_includes_before_after_counts(self):
        self._fixtures()

        payload = json.loads(self._call_apply("--format", "json"))
        row = next(action for action in payload["actions"] if action["username"] == "testuser")

        self.assertEqual(row["before_dependency_counts"]["spot_envelope_created_by"], 2)
        self.assertEqual(row["after_dependency_counts"]["spot_envelope_created_by"], 0)

    def test_missing_targets_fail_safely(self):
        testuser = CustomUser.objects.create_user(username="testuser")
        SpotPricingEnvelopeDB.objects.create(
            created_by=testuser,
            shipment_context_json={"origin": "POM", "destination": "LAE"},
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test trigger",
            expires_at=timezone.now(),
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        testuser.refresh_from_db()
        self.assertGreater(payload["summary"]["blocked"], 0)
        self.assertTrue(testuser.is_active)
        self.assertTrue(SpotPricingEnvelopeDB.objects.filter(created_by=testuser).exists())

    def test_readiness_improves_after_apply(self):
        self._fixtures()

        self._call_apply("--apply")
        stdout = StringIO()
        call_command("rbac_post_membership_apply_readiness", "--format", "json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["readiness"]["status"], "READY_FOR_BACKFILL_PLANNING")


class LegacyOrganizationCleanupTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        OperatingEntity.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_legacy_organization_cleanup_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _call_apply(self, *args):
        stdout = StringIO()
        call_command("rbac_legacy_organization_cleanup_apply", *args, stdout=stdout)
        return stdout.getvalue()

    def _role(self):
        role, _created = Role.objects.get_or_create(
            code="sales",
            organization=None,
            defaults={"name": "Sales", "is_system": True},
        )
        return role

    def _canonical_master_data(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        for name, branches in {
            "EFM PNG": ("Port Moresby", "Lae"),
            "EFM Australia": ("Brisbane",),
            "EFM Fiji": ("Suva",),
            "EFM Solomon Islands": ("Honiara",),
        }.items():
            entity = OperatingEntity.objects.create(
                organization=org,
                code=name.split()[-1][:3].upper(),
                name=name,
                slug=name.lower().replace(" ", "-"),
                country_code=name[:2].upper(),
            )
            for branch_name in branches:
                Branch.objects.create(organization=org, operating_entity=entity, code=branch_name[:3].upper(), name=branch_name)
        for department_name in ("Air Freight", "Sea Freight", "Customs", "Transport"):
            Department.objects.create(organization=org, code=department_name[:3].upper(), name=department_name)
        return org

    def test_plan_command_is_read_only_and_detects_dependencies(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        company = Company.objects.create(name="Legacy AU Customer", organization=legacy)
        before = (Organization.objects.count(), Company.objects.count())

        payload = json.loads(self._call_plan("--format", "json"))

        company.refresh_from_db()
        row = next(item for item in payload["organizations"] if item["name"] == "EFM Australia")
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(before, (Organization.objects.count(), Company.objects.count()))
        self.assertEqual(company.organization, legacy)
        self.assertGreaterEqual(row["dependency_count"], 1)

    def test_country_organization_dependency_is_planned_for_safe_migration(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        Company.objects.create(name="Legacy AU Customer", organization=legacy)

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(item for item in payload["organizations"] if item["name"] == "EFM Australia")
        dep = next(item for item in row["dependencies"] if item["model"] == "parties.Company" and item["field"] == "organization")
        self.assertEqual(row["recommended_action"], "migrate_references")
        self.assertTrue(dep["auto_migratable"])
        self.assertEqual(dep["target_organization"], "Express Freight Management")
        self.assertEqual(dep["target_operating_entity"], "EFM Australia")

    def test_non_inferable_branch_dependency_is_blocked(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        branch = Branch.objects.create(organization=legacy, code="MAD", name="Madang")
        Company.objects.create(name="Legacy Branch Customer", organization=legacy, branch=branch)

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(item for item in payload["organizations"] if item["name"] == "EFM PNG")
        dep = next(item for item in row["dependencies"] if item["model"] == "parties.Company" and item["field"] == "branch")
        self.assertFalse(dep["auto_migratable"])
        self.assertIn("target branch not inferable", dep["blockers"])
        self.assertEqual(row["recommended_action"], "manual_review_required")

    def test_dry_run_apply_writes_nothing(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Fiji", slug="efm-fiji-legacy")
        company = Company.objects.create(name="Legacy Fiji Customer", organization=legacy)

        payload = json.loads(self._call_apply("--format", "json"))

        company.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(company.organization, legacy)
        self.assertTrue(legacy.is_active)

    def test_apply_migrates_safe_records_and_is_idempotent(self):
        org = self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        branch = Branch.objects.get(organization=org, name="Port Moresby")
        department = Department.objects.get(organization=org, name="Air Freight")
        user = CustomUser.objects.create_user(username="legacy-png-user")
        membership = UserMembership.objects.create(
            user=user,
            organization=legacy,
            branch=branch,
            department=department,
            role=self._role(),
        )
        Company.objects.create(name="Legacy PNG Customer", organization=legacy)

        first = json.loads(self._call_apply("--apply", "--format", "json"))
        second = json.loads(self._call_apply("--apply", "--format", "json"))

        membership.refresh_from_db()
        legacy.refresh_from_db()
        self.assertGreater(first["summary"]["applied"], 0)
        self.assertGreaterEqual(second["summary"]["unchanged"], 1)
        self.assertEqual(membership.organization.name, "Express Freight Management")
        self.assertEqual(membership.operating_entity.name, "EFM PNG")
        self.assertFalse(legacy.is_active)

    def test_zero_dependency_legacy_organization_is_deactivated_only_after_apply(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Solomon Islands", slug="efm-solomon-islands-legacy")

        dry_run = json.loads(self._call_apply("--format", "json"))
        legacy.refresh_from_db()
        self.assertTrue(legacy.is_active)

        applied = json.loads(self._call_apply("--apply", "--format", "json"))
        legacy.refresh_from_db()
        self.assertFalse(legacy.is_active)
        self.assertGreaterEqual(dry_run["summary"]["planned"], 1)
        self.assertGreaterEqual(applied["summary"]["applied"], 1)

    def test_eac_is_legacy_air_freight_wording(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Express Air Cargo", slug="efm-express-air-cargo")
        user = CustomUser.objects.create_user(username="legacy-eac-user")
        UserMembership.objects.create(user=user, organization=legacy, role=self._role())

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(item for item in payload["organizations"] if item["name"] == "EFM Express Air Cargo")
        dep = next(item for item in row["dependencies"] if item["model"] == "accounts.UserMembership")
        self.assertEqual(row["classification"], "legacy_air_freight_wording")
        self.assertEqual(dep["target_department"], "Air Freight")
        self.assertIsNone(dep["target_operating_entity"])

    def test_test_org_is_not_blindly_migrated(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="Test Org", slug="test-org")
        Company.objects.create(name="Test Org Customer", organization=legacy)

        payload = json.loads(self._call_plan("--format", "json"))

        row = next(item for item in payload["organizations"] if item["name"] == "Test Org")
        self.assertEqual(row["classification"], "DEV_TEST_LEGACY")
        self.assertEqual(row["recommended_action"], "manual_review_required")
        self.assertIn("DEV_TEST_LEGACY manual review required", row["blockers"])

    def test_quote_records_are_classified_not_mutated(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        company = Company.objects.create(name="Quote Legacy Customer", organization=legacy)
        quote = Quote.objects.create(customer=company, organization=legacy)

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        quote.refresh_from_db()
        self.assertEqual(quote.organization, legacy)
        self.assertTrue(
            any(action["model"] == "quotes.Quote" and "DEV_TEST_LEGACY quote/SPOT historical record" in action["blockers"] for action in payload["actions"])
        )

    def test_legacy_country_org_can_be_deactivated_after_only_protected_dependencies_remain(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM Australia", slug="efm-australia")
        company = Company.objects.create(name="Protected Quote Customer", organization=legacy)
        Quote.objects.create(customer=company, organization=legacy)

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        legacy.refresh_from_db()
        self.assertFalse(legacy.is_active)
        self.assertTrue(any(action["organization"] == "EFM Australia" and action["field"] == "is_active" for action in payload["actions"]))

    def test_test_org_is_not_deactivated_with_dependencies(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="Test Org", slug="test-org")
        Company.objects.create(name="Test Org Customer With Dependency", organization=legacy)

        self._call_apply("--apply")

        legacy.refresh_from_db()
        self.assertTrue(legacy.is_active)


class DuplicateMasterDataConsolidationTests(TestCase):
    def setUp(self):
        UserMembership.objects.all().delete()
        CustomUser.objects.all().delete()
        Branch.objects.all().delete()
        OperatingEntity.objects.all().delete()
        Department.objects.all().delete()
        Organization.objects.all().delete()

    def _call_plan(self, *args):
        stdout = StringIO()
        call_command("rbac_duplicate_master_data_consolidation_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def _call_apply(self, *args):
        stdout = StringIO()
        call_command("rbac_duplicate_master_data_consolidation_apply", *args, stdout=stdout)
        return stdout.getvalue()

    def _canonical_master_data(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entity = OperatingEntity.objects.create(
            organization=org,
            code="PNG",
            name="EFM PNG",
            slug="efm-png",
            country_code="PG",
        )
        branch = Branch.objects.create(organization=org, operating_entity=entity, code="POM", name="Port Moresby")
        department = Department.objects.create(organization=org, code="AIR", name="Air Freight")
        return org, branch, department

    def test_plan_is_read_only_and_detects_duplicate_master_data(self):
        _org, branch, department = self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        duplicate_branch = Branch.objects.create(organization=legacy, code="POM", name="Port Moresby")
        duplicate_department = Department.objects.create(organization=legacy, code="AIR", name="Air Freight")
        before = (duplicate_branch.is_active, duplicate_department.is_active)

        payload = json.loads(self._call_plan("--format", "json"))

        duplicate_branch.refresh_from_db()
        duplicate_department.refresh_from_db()
        self.assertFalse(payload["write_enabled"])
        self.assertEqual(before, (duplicate_branch.is_active, duplicate_department.is_active))
        self.assertEqual(payload["branches"][0]["canonical_target"], f"Express Freight Management:{branch.code} {branch.name}")
        self.assertEqual(payload["departments"][0]["canonical_target"], f"Express Freight Management:{department.code} {department.name}")

    def test_dry_run_writes_nothing(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        duplicate_branch = Branch.objects.create(organization=legacy, code="POM", name="Port Moresby")
        company = Company.objects.create(name="Legacy Branch Customer", organization=legacy, branch=duplicate_branch)

        payload = json.loads(self._call_apply("--format", "json"))

        company.refresh_from_db()
        duplicate_branch.refresh_from_db()
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(company.branch, duplicate_branch)
        self.assertTrue(duplicate_branch.is_active)

    def test_apply_repoints_safe_branch_and_department_references(self):
        _org, canonical_branch, canonical_department = self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        duplicate_branch = Branch.objects.create(organization=legacy, code="POM", name="Port Moresby")
        duplicate_department = Department.objects.create(organization=legacy, code="AIR", name="Air Freight")
        company = Company.objects.create(
            name="Legacy Scoped Customer",
            organization=legacy,
            branch=duplicate_branch,
            department=duplicate_department,
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        company.refresh_from_db()
        duplicate_branch.refresh_from_db()
        duplicate_department.refresh_from_db()
        self.assertGreaterEqual(payload["summary"]["applied"], 2)
        self.assertEqual(company.branch, canonical_branch)
        self.assertEqual(company.department, canonical_department)
        self.assertFalse(duplicate_branch.is_active)
        self.assertFalse(duplicate_department.is_active)

    def test_quote_spot_historical_records_are_not_mutated(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        duplicate_branch = Branch.objects.create(organization=legacy, code="POM", name="Port Moresby")
        duplicate_department = Department.objects.create(organization=legacy, code="AIR", name="Air Freight")
        company = Company.objects.create(name="Legacy Quote Customer", organization=legacy)
        quote = Quote.objects.create(
            customer=company,
            organization=legacy,
            branch=duplicate_branch,
            department=duplicate_department,
        )

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        quote.refresh_from_db()
        duplicate_branch.refresh_from_db()
        duplicate_department.refresh_from_db()
        self.assertEqual(quote.branch, duplicate_branch)
        self.assertEqual(quote.department, duplicate_department)
        self.assertTrue(duplicate_branch.is_active)
        self.assertTrue(duplicate_department.is_active)
        self.assertTrue(any(action["model"] == "quotes.Quote" and action["status"] == "BLOCKED" for action in payload["actions"]))

    def test_test_org_duplicate_departments_are_manual_review_only(self):
        self._canonical_master_data()
        test_org = Organization.objects.create(name="Test Org", slug="test-org")
        duplicate_department = Department.objects.create(organization=test_org, code="AIR", name="Air Freight")

        payload = json.loads(self._call_apply("--apply", "--format", "json"))

        duplicate_department.refresh_from_db()
        row = next(item for item in payload["actions"] if item["source"] == "Test Org:AIR Air Freight")
        self.assertTrue(duplicate_department.is_active)
        self.assertEqual(row["status"], "UNCHANGED")

    def test_legacy_cleanup_plan_improves_after_consolidation(self):
        self._canonical_master_data()
        legacy = Organization.objects.create(name="EFM PNG", slug="efm-png-legacy")
        Branch.objects.create(organization=legacy, code="POM", name="Port Moresby")
        Department.objects.create(organization=legacy, code="AIR", name="Air Freight")
        before = StringIO()
        call_command("rbac_legacy_organization_cleanup_plan", "--format", "json", stdout=before)

        self._call_apply("--apply", "--format", "json")
        after = StringIO()
        call_command("rbac_legacy_organization_cleanup_plan", "--format", "json", stdout=after)

        before_row = next(item for item in json.loads(before.getvalue())["organizations"] if item["name"] == "EFM PNG")
        after_row = next(item for item in json.loads(after.getvalue())["organizations"] if item["name"] == "EFM PNG")
        self.assertGreater(before_row["blocked_dependency_count"], after_row["blocked_dependency_count"])


class CustomerListAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CustomUser.objects.create_user(
            username="admin-user",
            password="testpass123",
            role=CustomUser.ROLE_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_list_returns_company_name_contact_and_primary_address(self):
        company = Company.objects.create(
            name="Seed Customer",
            is_customer=True,
            company_type="CUSTOMER",
        )
        Contact.objects.create(
            company=company,
            first_name="Seed",
            last_name="Contact",
            email="seed.contact@example.com",
            is_primary=True,
            is_active=True,
        )
        country = Country.objects.create(code="PG", name="Papua New Guinea")
        city = City.objects.create(name="Port Moresby", country=country)
        Address.objects.create(
            company=company,
            address_line_1="Waigani Drive",
            city=city,
            country=country,
            is_primary=True,
        )

        response = self.client.get("/api/v3/customers/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        row = response.data[0]
        self.assertEqual(row["company_name"], "Seed Customer")
        self.assertEqual(row["name"], "Seed Customer")
        self.assertEqual(row["contact_person_name"], "Seed Contact")
        self.assertEqual(row["primary_address"]["country"], "PG")

    def test_list_includes_legacy_customer_rows_with_company_type_only(self):
        legacy = Company.objects.create(
            name="Legacy Customer",
            is_customer=False,
            company_type="CUSTOMER",
        )

        response = self.client.get("/api/v3/customers/")

        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data}
        self.assertIn(str(legacy.id), returned_ids)

    def test_list_excludes_archived_customers(self):
        active = Company.objects.create(
            name="Active Customer",
            is_customer=True,
            company_type="CUSTOMER",
            is_active=True,
        )
        archived = Company.objects.create(
            name="Archived Customer",
            is_customer=True,
            company_type="CUSTOMER",
            is_active=False,
        )

        response = self.client.get("/api/v3/customers/")

        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data}
        self.assertIn(str(active.id), returned_ids)
        self.assertNotIn(str(archived.id), returned_ids)

    def test_admin_create_populates_scope_from_single_active_membership(self):
        organization = Organization.objects.create(name="Create Org", slug="create-org", is_active=True)
        branch = Branch.objects.create(organization=organization, code="POM", name="Port Moresby")
        department = Department.objects.create(
            organization=organization,
            branch=branch,
            code="AIR",
            name="Air Freight",
        )
        role = Role.objects.create(code="admin", name="Admin", is_system=True)
        UserMembership.objects.create(
            user=self.admin,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
        )

        response = self.client.post(
            "/api/v3/customers/",
            {"name": "Scoped API Customer"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(name="Scoped API Customer")
        self.assertEqual(company.organization, organization)
        self.assertEqual(company.branch, branch)
        self.assertEqual(company.department, department)


class BackendScopedAccessAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.role_admin = Role.objects.create(code="phase9d-admin", name="Admin", is_system=True)
        self.role_manager = Role.objects.create(code="phase9d-manager", name="Manager", is_system=True)
        self.role_sales = Role.objects.create(code="phase9d-sales", name="Sales", is_system=True)

        self.org_a = Organization.objects.create(name="Phase 9D Org A", slug="phase-9d-org-a")
        self.operating_entity_a = OperatingEntity.objects.create(
            organization=self.org_a,
            code="P9PNG",
            name="Phase 9D PNG",
            slug="phase-9d-png",
            country_code="PG",
        )
        self.operating_entity_b = OperatingEntity.objects.create(
            organization=self.org_a,
            code="P9AU",
            name="Phase 9D Australia",
            slug="phase-9d-australia",
            country_code="AU",
        )
        self.branch_a = Branch.objects.create(
            organization=self.org_a,
            operating_entity=self.operating_entity_a,
            code="P9A",
            name="Phase 9D A",
        )
        self.department_a = Department.objects.create(
            organization=self.org_a,
            branch=self.branch_a,
            code="AIR",
            name="Air Freight",
        )
        self.department_a_other = Department.objects.create(
            organization=self.org_a,
            branch=self.branch_a,
            code="SEA",
            name="Sea Freight",
        )
        self.branch_a_other = Branch.objects.create(
            organization=self.org_a,
            operating_entity=self.operating_entity_a,
            code="P9A2",
            name="Phase 9D A2",
        )
        self.department_a_other_branch = Department.objects.create(
            organization=self.org_a,
            branch=self.branch_a_other,
            code="CUS",
            name="Customs",
        )
        self.branch_a_other_operating_entity = Branch.objects.create(
            organization=self.org_a,
            operating_entity=self.operating_entity_b,
            code="P9AU",
            name="Phase 9D AU",
        )
        self.department_a_other_operating_entity = Department.objects.create(
            organization=self.org_a,
            branch=self.branch_a_other_operating_entity,
            code="TRN",
            name="Transport",
        )
        self.org_b = Organization.objects.create(name="Phase 9D Org B", slug="phase-9d-org-b")
        self.branch_b = Branch.objects.create(organization=self.org_b, code="P9B", name="Phase 9D B")
        self.department_b = Department.objects.create(
            organization=self.org_b,
            branch=self.branch_b,
            code="AIR",
            name="Air Freight",
        )

        self.admin = self._user("phase9d-admin-user", CustomUser.ROLE_ADMIN, self.org_a, self.branch_a, self.department_a, self.role_admin)
        self.manager = self._user("phase9d-manager-user", CustomUser.ROLE_MANAGER, self.org_a, self.branch_a, self.department_a, self.role_manager)
        self.sales = self._user("phase9d-sales-user", CustomUser.ROLE_SALES, self.org_a, self.branch_a, self.department_a, self.role_sales)

        self.company_a = self._company("Phase 9D Customer A", self.org_a, self.branch_a, self.department_a)
        self.company_a_other_department = self._company(
            "Phase 9D Customer A Same Branch Other Department",
            self.org_a,
            self.branch_a,
            self.department_a_other,
        )
        self.company_a_other_branch = self._company(
            "Phase 9D Customer A Other Branch",
            self.org_a,
            self.branch_a_other,
            self.department_a_other_branch,
        )
        self.company_a_other_operating_entity = self._company(
            "Phase 9D Customer A Other Operating Entity",
            self.org_a,
            self.branch_a_other_operating_entity,
            self.department_a_other_operating_entity,
        )
        self.company_b = self._company("Phase 9D Customer B", self.org_b, self.branch_b, self.department_b)
        self.company_unscoped = Company.objects.create(
            name="Phase 9D Manual Review Customer",
            is_customer=True,
            company_type="CUSTOMER",
        )
        self.contact_a = self._contact(self.company_a, "a")
        self.contact_a_other_department = self._contact(self.company_a_other_department, "a-other-department")
        self.contact_a_other_branch = self._contact(self.company_a_other_branch, "a-other-branch")
        self.contact_a_other_operating_entity = self._contact(
            self.company_a_other_operating_entity,
            "a-other-operating-entity",
        )
        self.contact_b = self._contact(self.company_b, "b")
        self.company_a_other = self._company("Phase 9D Customer A Other", self.org_a, self.branch_a, self.department_a)
        self.contact_a_other = self._contact(self.company_a_other, "a-other")

        self.opportunity_a = self._opportunity("Phase 9D Opportunity A", self.company_a, self.org_a, self.branch_a, self.department_a)
        self.opportunity_a_other_department = self._opportunity(
            "Phase 9D Opportunity A Other Department",
            self.company_a_other_department,
            self.org_a,
            self.branch_a,
            self.department_a_other,
        )
        self.opportunity_a_other_branch = self._opportunity(
            "Phase 9D Opportunity A Other Branch",
            self.company_a_other_branch,
            self.org_a,
            self.branch_a_other,
            self.department_a_other_branch,
        )
        self.opportunity_b = self._opportunity("Phase 9D Opportunity B", self.company_b, self.org_b, self.branch_b, self.department_b)
        self.interaction_a = self._interaction(self.company_a, self.org_a, self.branch_a, self.department_a)
        self.interaction_a_other_department = self._interaction(
            self.company_a_other_department,
            self.org_a,
            self.branch_a,
            self.department_a_other,
        )
        self.interaction_a_other_branch = self._interaction(
            self.company_a_other_branch,
            self.org_a,
            self.branch_a_other,
            self.department_a_other_branch,
        )
        self.interaction_b = self._interaction(self.company_b, self.org_b, self.branch_b, self.department_b)
        self.task_a = self._task("Phase 9D Task A", self.company_a, self.org_a, self.branch_a, self.department_a)
        self.task_a_other_department = self._task(
            "Phase 9D Task A Other Department",
            self.company_a_other_department,
            self.org_a,
            self.branch_a,
            self.department_a_other,
        )
        self.task_a_other_branch = self._task(
            "Phase 9D Task A Other Branch",
            self.company_a_other_branch,
            self.org_a,
            self.branch_a_other,
            self.department_a_other_branch,
        )
        self.task_b = self._task("Phase 9D Task B", self.company_b, self.org_b, self.branch_b, self.department_b)

    def _user(self, username, role, organization, branch, department, membership_role):
        user = CustomUser.objects.create_user(username=username, password="testpass123", role=role)
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=membership_role,
        )
        return user

    def _company(self, name, organization, branch, department):
        return Company.objects.create(
            name=name,
            is_customer=True,
            company_type="CUSTOMER",
            organization=organization,
            branch=branch,
            department=department,
        )

    def _contact(self, company, suffix):
        return Contact.objects.create(
            company=company,
            organization=company.organization,
            branch=company.branch,
            department=company.department,
            first_name="Phase",
            last_name=f"Contact {suffix}",
            email=f"phase9d-{suffix}@example.com",
            is_active=True,
        )

    def _opportunity(self, title, company, organization, branch, department):
        return Opportunity.objects.create(
            company=company,
            title=title,
            service_type="AIR",
            owner=self.sales,
            organization=organization,
            branch=branch,
            department=department,
        )

    def _interaction(self, company, organization, branch, department):
        return Interaction.objects.create(
            company=company,
            interaction_type=Interaction.InteractionType.CALL,
            summary=f"Call with {company.name}",
            author=self.sales,
            organization=organization,
            branch=branch,
            department=department,
        )

    def _task(self, description, company, organization, branch, department):
        return Task.objects.create(
            company=company,
            description=description,
            owner=self.sales,
            due_date=timezone.now().date(),
            organization=organization,
            branch=branch,
            department=department,
        )

    def _spot_envelope(self):
        return SpotPricingEnvelopeDB.objects.create(
            created_by=self.sales,
            owner=self.sales,
            shipment_context_json={"origin": "POM", "destination": "LAE"},
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test trigger",
            expires_at=timezone.now(),
        )

    def _ids(self, response):
        return {str(row["id"]) for row in response.data}

    def test_admin_can_access_cross_scope_customers(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/v3/customers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._ids(response)
        self.assertIn(str(self.company_a.id), returned_ids)
        self.assertIn(str(self.company_a_other_department.id), returned_ids)
        self.assertIn(str(self.company_a_other_branch.id), returned_ids)
        self.assertIn(str(self.company_a_other_operating_entity.id), returned_ids)
        self.assertIn(str(self.company_b.id), returned_ids)
        self.assertIn(str(self.company_unscoped.id), returned_ids)

    def test_scoped_manager_can_access_in_scope_customer(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get(f"/api/v3/customers/{self.company_a_other_branch.id}/")
        other_operating_entity = self.client.get(f"/api/v3/customers/{self.company_a_other_operating_entity.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.company_a_other_branch.id))
        self.assertEqual(other_operating_entity.status_code, status.HTTP_404_NOT_FOUND)

    def test_scoped_user_list_includes_same_operating_entity_and_excludes_out_of_scope_customers(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get("/api/v3/customers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._ids(response)
        self.assertIn(str(self.company_a.id), returned_ids)
        self.assertIn(str(self.company_a_other_department.id), returned_ids)
        self.assertIn(str(self.company_a_other_branch.id), returned_ids)
        self.assertNotIn(str(self.company_a_other_operating_entity.id), returned_ids)
        self.assertNotIn(str(self.company_b.id), returned_ids)
        self.assertNotIn(str(self.company_unscoped.id), returned_ids)

    def test_scoped_user_cannot_retrieve_out_of_scope_customer_by_id(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get(f"/api/v3/customers/{self.company_b.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_scoped_user_can_retrieve_same_operating_entity_customer_from_other_branch(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get(f"/api/v3/customers/{self.company_a_other_branch.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.company_a_other_branch.id))

    def test_customer_detail_uses_operating_entity_visible_customer_scope(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get(f"/api/v3/customer-details/{self.company_a_other_branch.id}/")
        other_operating_entity = self.client.get(
            f"/api/v3/customer-details/{self.company_a_other_operating_entity.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.company_a_other_branch.id))
        self.assertEqual(other_operating_entity.status_code, status.HTTP_404_NOT_FOUND)

    def test_company_selector_filters_out_of_scope_companies(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get("/api/v3/parties/search/", {"q": "Phase 9D Customer"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._ids(response)
        self.assertIn(str(self.company_a.id), returned_ids)
        self.assertIn(str(self.company_a_other_department.id), returned_ids)
        self.assertIn(str(self.company_a_other_branch.id), returned_ids)
        self.assertNotIn(str(self.company_a_other_operating_entity.id), returned_ids)
        self.assertNotIn(str(self.company_b.id), returned_ids)

    def test_contact_by_company_endpoint_checks_parent_company_scope(self):
        self.client.force_authenticate(user=self.sales)

        in_scope = self.client.get(f"/api/v3/parties/companies/{self.company_a.id}/contacts/")
        same_branch_other_department = self.client.get(
            f"/api/v3/parties/companies/{self.company_a_other_department.id}/contacts/"
        )
        same_operating_entity_other_branch = self.client.get(
            f"/api/v3/parties/companies/{self.company_a_other_branch.id}/contacts/"
        )
        other_operating_entity = self.client.get(
            f"/api/v3/parties/companies/{self.company_a_other_operating_entity.id}/contacts/"
        )
        out_of_scope = self.client.get(f"/api/v3/parties/companies/{self.company_b.id}/contacts/")

        self.assertEqual(in_scope.status_code, status.HTTP_200_OK)
        self.assertEqual(self._ids(in_scope), {str(self.contact_a.id)})
        self.assertEqual(same_branch_other_department.status_code, status.HTTP_200_OK)
        self.assertEqual(self._ids(same_branch_other_department), {str(self.contact_a_other_department.id)})
        self.assertEqual(same_operating_entity_other_branch.status_code, status.HTTP_200_OK)
        self.assertEqual(self._ids(same_operating_entity_other_branch), {str(self.contact_a_other_branch.id)})
        self.assertEqual(other_operating_entity.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(out_of_scope.status_code, status.HTTP_404_NOT_FOUND)

    def test_crm_viewsets_filter_and_deny_direct_out_of_scope_ids(self):
        self.client.force_authenticate(user=self.sales)

        opportunity_list = self.client.get("/api/v3/crm/opportunities/")
        interaction_list = self.client.get("/api/v3/crm/interactions/")
        task_list = self.client.get("/api/v3/crm/tasks/")

        self.assertEqual(opportunity_list.status_code, status.HTTP_200_OK)
        self.assertEqual(interaction_list.status_code, status.HTTP_200_OK)
        self.assertEqual(task_list.status_code, status.HTTP_200_OK)
        self.assertIn(str(self.opportunity_a.id), self._ids(opportunity_list))
        self.assertNotIn(str(self.opportunity_a_other_department.id), self._ids(opportunity_list))
        self.assertNotIn(str(self.opportunity_a_other_branch.id), self._ids(opportunity_list))
        self.assertNotIn(str(self.opportunity_b.id), self._ids(opportunity_list))
        self.assertIn(str(self.interaction_a.id), self._ids(interaction_list))
        self.assertNotIn(str(self.interaction_a_other_department.id), self._ids(interaction_list))
        self.assertNotIn(str(self.interaction_a_other_branch.id), self._ids(interaction_list))
        self.assertNotIn(str(self.interaction_b.id), self._ids(interaction_list))
        self.assertIn(str(self.task_a.id), self._ids(task_list))
        self.assertNotIn(str(self.task_a_other_department.id), self._ids(task_list))
        self.assertNotIn(str(self.task_a_other_branch.id), self._ids(task_list))
        self.assertNotIn(str(self.task_b.id), self._ids(task_list))

        self.assertEqual(
            self.client.get(f"/api/v3/crm/opportunities/{self.opportunity_a_other_department.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/opportunities/{self.opportunity_a_other_branch.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/interactions/{self.interaction_a_other_department.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/interactions/{self.interaction_a_other_branch.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/tasks/{self.task_a_other_department.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/tasks/{self.task_a_other_branch.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/opportunities/{self.opportunity_b.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/interactions/{self.interaction_b.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/v3/crm/tasks/{self.task_b.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_quote_calculation_rejects_out_of_scope_customer_id_before_pricing(self):
        self.client.force_authenticate(user=self.sales)
        pgk = Currency.objects.create(code="PGK", name="Papua New Guinean Kina")
        png = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)
        pom = Location.objects.create(code="POM", name="Port Moresby", country=png)
        lae = Location.objects.create(code="LAE", name="Lae", country=png)

        response = self.client.post(
            "/api/v3/quotes/compute/",
            {
                "customer_id": str(self.company_b.id),
                "contact_id": str(self.contact_b.id),
                "mode": "AIR",
                "service_scope": "D2D",
                "origin_location_id": str(pom.id),
                "destination_location_id": str(lae.id),
                "incoterm": "DAP",
                "payment_term": "PREPAID",
                "dimensions": [
                    {
                        "pieces": 1,
                        "length_cm": "10",
                        "width_cm": "10",
                        "height_cm": "10",
                        "gross_weight_kg": "1",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_spot_quote_creation_rejects_out_of_scope_customer_id(self):
        self.client.force_authenticate(user=self.sales)
        envelope = self._spot_envelope()

        response = self.client.post(
            f"/api/v3/spot/envelopes/{envelope.id}/create-quote/",
            {"customer_id": str(self.company_b.id)},
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND})
        if response.status_code == status.HTTP_404_NOT_FOUND:
            self.assertEqual(response.data["error"], "Selected customer is not available for this user.")

    def test_spot_quote_creation_rejects_out_of_scope_contact_id(self):
        self.client.force_authenticate(user=self.sales)
        envelope = self._spot_envelope()

        response = self.client.post(
            f"/api/v3/spot/envelopes/{envelope.id}/create-quote/",
            {
                "customer_id": str(self.company_a.id),
                "contact_id": str(self.contact_b.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Selected contact is not available for this customer/user.")

    def test_spot_quote_creation_rejects_contact_id_for_different_scoped_customer(self):
        self.client.force_authenticate(user=self.sales)
        envelope = self._spot_envelope()

        response = self.client.post(
            f"/api/v3/spot/envelopes/{envelope.id}/create-quote/",
            {
                "customer_id": str(self.company_a.id),
                "contact_id": str(self.contact_a_other.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Selected contact is not available for this customer/user.")

    def test_spot_quote_creation_allows_customer_only_request_to_reach_existing_validation(self):
        self.client.force_authenticate(user=self.sales)
        envelope = self._spot_envelope()

        response = self.client.post(
            f"/api/v3/spot/envelopes/{envelope.id}/create-quote/",
            {"customer_id": str(self.company_a.id)},
            format="json",
        )

        self.assertNotEqual(
            response.data.get("error"),
            "Selected contact is not available for this customer/user.",
        )


class OrganizationBrandingSettingsAPITests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="branding-admin",
            password="testpass123",
            role=CustomUser.ROLE_ADMIN,
        )
        self.sales = CustomUser.objects.create_user(
            username="branding-sales",
            password="testpass123",
            role=CustomUser.ROLE_SALES,
        )
        pgk = Currency.objects.filter(code="PGK").first() or Currency.objects.create(
            code="PGK",
            name="Papua New Guinean Kina",
        )
        self.organization, _ = Organization.objects.get_or_create(
            slug="efm-express-air-cargo",
            defaults={
                "name": "EFM Express Air Cargo",
                "default_currency": pgk,
                "is_active": True,
            },
        )
        self.branding, _ = OrganizationBranding.objects.update_or_create(
            organization=self.organization,
            defaults={
                "display_name": "EFM Express Air Cargo",
                "support_email": "quotes@efmexpress.com",
                "support_phone": "+675 325 8500",
                "primary_color": "#0F2A56",
                "accent_color": "#D71920",
            },
        )
        self.url = reverse("parties:organization-branding-settings-v3")

    def test_admin_can_get_branding_settings(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], "EFM Express Air Cargo")
        self.assertEqual(response.data["organization_slug"], "efm-express-air-cargo")

    def test_sales_cannot_get_branding_settings(self):
        self.client.force_authenticate(user=self.sales)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_patch_branding_settings(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            self.url,
            {
                "display_name": "EFM Cargo",
                "support_phone": "+675 123 4567",
                "public_quote_tagline": "Fast PNG airfreight quotes",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.branding.refresh_from_db()
        self.assertEqual(self.branding.display_name, "EFM Cargo")
        self.assertEqual(self.branding.support_phone, "+675 123 4567")
        self.assertEqual(self.branding.public_quote_tagline, "Fast PNG airfreight quotes")

    def test_settings_resolve_from_authenticated_users_organization(self):
        aud = Currency.objects.filter(code="AUD").first() or Currency.objects.create(
            code="AUD",
            name="Australian Dollar",
        )
        other_org = Organization.objects.create(
            name="Second Tenant",
            slug="second-tenant",
            default_currency=aud,
            is_active=True,
        )
        OrganizationBranding.objects.create(
            organization=other_org,
            display_name="Second Tenant",
            support_email="ops@second.example",
            is_active=True,
        )
        self.admin.organization = other_org
        self.admin.save(update_fields=["organization"])
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["organization_slug"], "second-tenant")
        self.assertEqual(response.data["display_name"], "Second Tenant")

    def test_branding_settings_reject_invalid_logo_upload(self):
        self.client.force_authenticate(user=self.admin)
        invalid_logo = SimpleUploadedFile(
            "logo.txt",
            b"not-an-image",
            content_type="text/plain",
        )

        response = self.client.patch(
            self.url,
            {"logo_primary": invalid_logo},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("logo_primary", response.data)

    def test_branding_settings_return_public_logo_endpoint_url(self):
        self.client.force_authenticate(user=self.admin)
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color="#0F2A56").save(buffer, format="PNG")
        buffer.seek(0)
        valid_logo = SimpleUploadedFile("logo.png", buffer.read(), content_type="image/png")

        response = self.client.patch(
            self.url,
            {"logo_primary": valid_logo},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("/api/v3/public/branding/efm-express-air-cargo/primary/", response.data["logo_primary_url"])

    def test_branding_settings_hide_missing_logo_urls_and_flag_missing_file(self):
        self.client.force_authenticate(user=self.admin)
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color="#0F2A56").save(buffer, format="PNG")
        buffer.seek(0)
        valid_logo = SimpleUploadedFile("logo.png", buffer.read(), content_type="image/png")
        self.branding.logo_primary.save("logo.png", valid_logo, save=True)
        self.branding.logo_primary.storage.delete(self.branding.logo_primary.name)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["logo_primary_url"])
        self.assertTrue(response.data["logo_primary_missing"])


class CustomerDetailAPITests(APITestCase):
    def setUp(self):
        # Create organizations
        self.org_a = Organization.objects.create(name="Org A", slug="org-a", is_active=True)
        self.org_b = Organization.objects.create(name="Org B", slug="org-b", is_active=True)
        self.branch_a = Branch.objects.create(organization=self.org_a, code="OA", name="Org A Branch")
        self.branch_b = Branch.objects.create(organization=self.org_b, code="OB", name="Org B Branch")
        self.department_a = Department.objects.create(
            organization=self.org_a,
            branch=self.branch_a,
            code="AIR",
            name="Air Freight",
        )
        self.department_b = Department.objects.create(
            organization=self.org_b,
            branch=self.branch_b,
            code="AIR",
            name="Air Freight",
        )
        self.sales_role = Role.objects.create(code="customer-detail-sales", name="Sales", is_system=True)

        # Create users
        self.admin = CustomUser.objects.create_user(
            username="admin-user", password="password123", role=CustomUser.ROLE_ADMIN, organization=self.org_a
        )
        self.user_org_a = CustomUser.objects.create_user(
            username="user-org-a", password="password123", role=CustomUser.ROLE_SALES, organization=self.org_a
        )
        self.user_org_b = CustomUser.objects.create_user(
            username="user-org-b", password="password123", role=CustomUser.ROLE_SALES, organization=self.org_b
        )
        UserMembership.objects.create(
            user=self.user_org_a,
            organization=self.org_a,
            branch=self.branch_a,
            department=self.department_a,
            role=self.sales_role,
        )
        UserMembership.objects.create(
            user=self.user_org_b,
            organization=self.org_b,
            branch=self.branch_b,
            department=self.department_b,
            role=self.sales_role,
        )

        # Create customers
        self.customer_org_a = Company.objects.create(
            name="Customer Org A",
            is_customer=True,
            company_type="CUSTOMER",
            account_owner=self.user_org_a,
            organization=self.org_a,
            branch=self.branch_a,
            department=self.department_a,
        )
        self.customer_unowned = Company.objects.create(
            name="Customer Unowned", is_customer=True, company_type="CUSTOMER", account_owner=None
        )

    def test_admin_can_retrieve_any_customer(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_org_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["company_name"], "Customer Org A")

        url_unowned = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_unowned.id})
        response_unowned = self.client.get(url_unowned)
        self.assertEqual(response_unowned.status_code, status.HTTP_200_OK)
        self.assertEqual(response_unowned.data["company_name"], "Customer Unowned")

    def test_same_organization_user_can_retrieve_customer(self):
        self.client.force_authenticate(user=self.user_org_a)
        url = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_org_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["company_name"], "Customer Org A")

    def test_cross_organization_user_gets_404(self):
        self.client.force_authenticate(user=self.user_org_b)
        url = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_org_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unscoped_customer_is_blocked_for_non_admin_even_when_linked(self):
        self.client.force_authenticate(user=self.user_org_a)
        url = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_unowned.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        from quotes.models import Quote
        Quote.objects.create(
            customer=self.customer_unowned,
            organization=self.org_a,
            status=Quote.Status.DRAFT,
            mode="AIR",
            created_by=self.user_org_a
        )

        response_after_linked = self.client.get(url)
        self.assertEqual(response_after_linked.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(user=self.user_org_b)
        response_org_b = self.client.get(url)
        self.assertEqual(response_org_b.status_code, status.HTTP_404_NOT_FOUND)

