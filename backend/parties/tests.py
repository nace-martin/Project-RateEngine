import os
import tempfile
from io import StringIO
import csv

from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from accounts.models import CustomUser
from core.models import Country, City
from core.models import Currency
from parties.models import Company, Contact, Address, Organization, OrganizationBranding


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
