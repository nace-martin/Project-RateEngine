import os
import tempfile
from io import StringIO
import csv
import json
from io import BytesIO

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from PIL import Image

from accounts.models import CustomUser, Role, UserMembership
from crm.models import Interaction, Opportunity, Task
from core.models import Country, City
from core.models import Currency
from parties.models import Branch, Company, Contact, Address, Department, Organization, OrganizationBranding
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
        self.assertIn("operating entity", payload["model_assessment"]["organization_role"])
        self.assertFalse(payload["model_assessment"]["can_represent_intended_hierarchy"])

    def test_report_detects_intended_hierarchy_mismatches(self):
        efm_png = Organization.objects.create(name="EFM PNG", slug="efm-png")
        Branch.objects.create(organization=efm_png, code="POM", name="Port Moresby")
        Organization.objects.create(name="Legacy Workspace", slug="legacy-workspace")

        payload = json.loads(self._call_report("--format", "json"))

        mismatches = payload["mismatches"]
        self.assertNotIn("EFM PNG", mismatches["missing_operating_entities"])
        self.assertIn("EFM Australia", mismatches["missing_operating_entities"])
        self.assertIn("Legacy Workspace", mismatches["extra_organizations"])
        self.assertIn("Lae", mismatches["missing_branches_by_entity"]["EFM PNG"])

    def test_report_counts_active_memberships_missing_branch(self):
        organization = Organization.objects.create(name="EFM PNG", slug="efm-png")
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
        organization = Organization.objects.create(name="EFM PNG", slug="efm-png")
        branch = Branch.objects.create(organization=organization, code="POM", name="Port Moresby")
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

        # Create customers
        self.customer_org_a = Company.objects.create(
            name="Customer Org A", is_customer=True, company_type="CUSTOMER", account_owner=self.user_org_a
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

    def test_unowned_customer_is_blocked_for_non_admin_unless_linked(self):
        # 1. Unowned customer is blocked when not linked to any quotes in the organization
        self.client.force_authenticate(user=self.user_org_a)
        url = reverse("quotes:customer-detail", kwargs={"customer_id": self.customer_unowned.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # 2. Link unowned customer to a quote in Org A
        from quotes.models import Quote
        Quote.objects.create(
            customer=self.customer_unowned,
            organization=self.org_a,
            status=Quote.Status.DRAFT,
            mode="AIR",
            created_by=self.user_org_a
        )

        # 3. Should now be retrievable for user in Org A
        response_after_linked = self.client.get(url)
        self.assertEqual(response_after_linked.status_code, status.HTTP_200_OK)
        self.assertEqual(response_after_linked.data["company_name"], "Customer Unowned")

        # 4. But still blocked for user in Org B
        self.client.force_authenticate(user=self.user_org_b)
        response_org_b = self.client.get(url)
        self.assertEqual(response_org_b.status_code, status.HTTP_404_NOT_FOUND)

