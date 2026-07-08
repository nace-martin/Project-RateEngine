import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import Role, UserMembership
from core.models import Airport, City, Country, Currency, Location
from core.tests.helpers import create_location
from parties.models import Branch, Company, Department, OperatingEntity, Organization
from pricing_v4.models import ChargeAlias, ProductCode


class AirFreightPilotSeedAuditCommandTests(TestCase):
    def call_audit(self, *args):
        stdout = StringIO()
        call_command("air_freight_pilot_seed_audit", *args, stdout=stdout)
        return stdout.getvalue()

    def payload(self):
        return json.loads(self.call_audit("--format", "json"))

    def test_command_performs_no_writes(self):
        before = self.counts()
        self.payload()
        self.call_audit("--format", "text")
        self.assertEqual(before, self.counts())

    def test_missing_data_is_reported_as_missing(self):
        payload = self.payload()
        self.assertEqual(payload["status"], "not_ready")
        self.assertIn({"section": "hierarchy.organization", "item": "Express Freight Management"}, payload["missing"])
        self.assertIn({"section": "currencies", "item": "PGK"}, payload["missing"])

    def test_existing_canonical_data_is_reported_as_existing(self):
        self.create_hierarchy()
        payload = self.payload()
        self.assertTrue(payload["hierarchy"]["organization"]["exists"])
        self.assertEqual(payload["hierarchy"]["branches"]["missing_count"], 0)
        self.assertEqual(payload["hierarchy"]["departments"]["missing_count"], 0)
        self.assertEqual(payload["hierarchy"]["operating_entities"]["missing_count"], 0)

    def test_product_code_conflicts_are_reported(self):
        self.product(1001, "AIRFRT", "Air Freight")
        self.product(1002, "AIR-FREIGHT-ALT", "Air Freight alternate")
        payload = self.payload()
        self.assertTrue(any("Air Freight" in row["detail"] for row in payload["conflicts"]))

    def test_missing_product_code_coverage_is_reported(self):
        payload = self.payload()
        self.assertIn({"section": "product_codes", "item": "fuel_surcharge"}, payload["missing"])
        self.assertGreater(payload["product_codes"]["missing_count"], 0)

    def test_missing_aliases_are_reported(self):
        payload = self.payload()
        self.assertIn({"section": "charge_aliases", "item": "fsc"}, payload["missing"])

    def test_missing_locations_and_currencies_are_reported(self):
        payload = self.payload()
        self.assertIn({"section": "locations", "item": "POM"}, payload["missing"])
        self.assertIn({"section": "currencies", "item": "USD"}, payload["missing"])

    def test_json_output_is_valid_and_stable(self):
        payload = self.payload()
        self.assertEqual(
            list(payload.keys()),
            [
                "charge_aliases",
                "conflicts",
                "currencies",
                "hierarchy",
                "locations",
                "missing",
                "pilot_data",
                "product_codes",
                "recommended_next_actions",
                "roles_memberships",
                "status",
                "summary",
                "warnings",
            ],
        )

    def test_text_output_works(self):
        output = self.call_audit("--format", "text")
        self.assertIn("Air Freight pilot seed audit:", output)
        self.assertIn("Recommended next actions:", output)

    def test_existing_alias_and_location_currency_are_reported(self):
        currency = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
        country = Country.objects.create(code="PG", name="Papua New Guinea", currency=currency)
        city = City.objects.create(country=country, name="Port Moresby")
        airport = Airport.objects.create(iata_code="POM", name="Jacksons International", city=city)
        create_location(code="POM", name="Port Moresby", kind=Location.Kind.AIRPORT, country=country, city=city, airport=airport)
        product = self.product(1001, "AIRFRT", "Air Freight")
        ChargeAlias.objects.create(
            alias_text="air freight",
            normalized_alias_text="air freight",
            product_code=product,
            is_active=True,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )

        payload = self.payload()
        self.assertTrue(payload["currencies"]["items"]["PGK"]["exists"])
        self.assertTrue(payload["locations"]["items"]["POM"]["exists"])
        self.assertTrue(payload["charge_aliases"]["aliases"]["air freight"]["exists"])

    def create_hierarchy(self):
        org = Organization.objects.create(name="Express Freight Management", slug="express-freight-management")
        entities = {
            code: OperatingEntity.objects.create(organization=org, code=code, name=name, slug=code.lower(), country_code="PG")
            for code, name in [
                ("PNG", "EFM PNG"),
                ("AUS", "EFM Australia"),
                ("FJI", "EFM Fiji"),
                ("SLB", "EFM Solomon Islands"),
            ]
        }
        for code, name in [("POM", "Port Moresby"), ("LAE", "Lae"), ("BNE", "Brisbane"), ("SUV", "Suva"), ("HIR", "Honiara")]:
            Branch.objects.create(organization=org, operating_entity=entities["PNG"], code=code, name=name)
        for code, name in [("AIR", "Air Freight"), ("SEA", "Sea Freight"), ("CUS", "Customs"), ("TRN", "Transport")]:
            Department.objects.create(organization=org, code=code, name=name)
        for code in ["admin", "manager", "sales", "finance"]:
            Role.objects.create(code=code, name=code.title(), is_system=True)
        Company.objects.create(name="Demo Customer", is_customer=True, organization=org)
        return org

    def product(self, pk, code, description):
        return ProductCode.objects.create(
            id=pk,
            code=code,
            description=description,
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_rate="0.0000",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="REV",
            gl_cost_code="COS",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def counts(self):
        return {
            "organization": Organization.objects.count(),
            "operating_entity": OperatingEntity.objects.count(),
            "branch": Branch.objects.count(),
            "department": Department.objects.count(),
            "role": Role.objects.count(),
            "membership": UserMembership.objects.count(),
            "product_code": ProductCode.objects.count(),
            "charge_alias": ChargeAlias.objects.count(),
            "currency": Currency.objects.count(),
            "airport": Airport.objects.count(),
            "location": Location.objects.count(),
            "company": Company.objects.count(),
        }
