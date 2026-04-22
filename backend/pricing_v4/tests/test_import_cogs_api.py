from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from pricing_v4.models import Agent, Carrier, ImportCOGS, ProductCode


class ImportCOGSAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="import-admin",
            password="testpass123",
            role="admin",
        )
        self.manager = User.objects.create_user(
            username="import-manager",
            password="testpass123",
            role="manager",
        )
        self.sales = User.objects.create_user(
            username="import-sales",
            password="testpass123",
            role="sales",
        )
        self.finance = User.objects.create_user(
            username="import-finance",
            password="testpass123",
            role="finance",
        )

        self.product_code = ProductCode.objects.create(
            id=2007,
            code="IMP-FRT-API",
            description="Import Freight API Test",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal("0.1000"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_KG,
        )
        self.agent = Agent.objects.create(
            code="EFM-AU",
            name="EFM Australia",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.carrier = Carrier.objects.create(
            code="PX",
            name="Air Niugini",
            carrier_type="AIRLINE",
        )
        self.today = timezone.localdate()

    def _payload(self, **overrides):
        payload = {
            "product_code": self.product_code.id,
            "origin_airport": "SYD",
            "destination_airport": "POM",
            "agent": self.agent.id,
            "carrier": None,
            "currency": "AUD",
            "rate_per_kg": "4.2500",
            "rate_per_shipment": None,
            "min_charge": "100.00",
            "max_charge": None,
            "is_additive": False,
            "percent_rate": None,
            "weight_breaks": None,
            "valid_from": str(self.today),
            "valid_until": str(self.today + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def test_sales_cannot_list_import_cogs(self):
        self.client.force_authenticate(self.sales)

        response = self.client.get("/api/v4/rates/import-cogs/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_cannot_create_import_cogs(self):
        self.client.force_authenticate(self.finance)

        response = self.client.post("/api/v4/rates/import-cogs/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_create_import_cogs_and_audit_fields_are_populated(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post("/api/v4/rates/import-cogs/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        row = ImportCOGS.objects.get(pk=response.data["id"])
        self.assertEqual(row.created_by, self.manager)
        self.assertEqual(row.updated_by, self.manager)
        self.assertEqual(response.data["created_by_username"], "import-manager")
        self.assertEqual(response.data["updated_by_username"], "import-manager")

    def test_admin_patch_updates_updated_by(self):
        row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("4.25"),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30),
            created_by=self.manager,
            updated_by=self.manager,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f"/api/v4/rates/import-cogs/{row.id}/",
            {"rate_per_kg": "4.5000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row.refresh_from_db()
        self.assertEqual(row.rate_per_kg, Decimal("4.5000"))
        self.assertEqual(row.created_by, self.manager)
        self.assertEqual(row.updated_by, self.admin)

    def test_rejects_invalid_effective_dates(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            "/api/v4/rates/import-cogs/",
            self._payload(valid_until=str(self.today)),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("valid_until", response.data)

    def test_rejects_negative_numeric_values(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            "/api/v4/rates/import-cogs/",
            self._payload(rate_per_kg="-1.00"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rate_per_kg", response.data)

    def test_rejects_unsorted_weight_breaks(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            "/api/v4/rates/import-cogs/",
            self._payload(
                rate_per_kg=None,
                min_charge=None,
                weight_breaks=[
                    {"min_kg": 100, "rate": "4.10"},
                    {"min_kg": 0, "rate": "4.50"},
                ],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("weight_breaks", response.data)

    def test_rejects_conflicting_amount_bases(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            "/api/v4/rates/import-cogs/",
            self._payload(
                rate_per_kg="4.25",
                weight_breaks=[{"min_kg": 0, "rate": "4.50"}],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("weight_breaks", response.data)

    def test_rejects_overlapping_effective_dates_for_same_key(self):
        ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("4.25"),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=10),
            created_by=self.manager,
            updated_by=self.manager,
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            "/api/v4/rates/import-cogs/",
            self._payload(
                valid_from=str(self.today + timedelta(days=5)),
                valid_until=str(self.today + timedelta(days=20)),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("valid_from", response.data)

    def test_delete_rejects_active_rows(self):
        row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("4.25"),
            valid_from=self.today - timedelta(days=5),
            valid_until=self.today + timedelta(days=10),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.delete(f"/api/v4/rates/import-cogs/{row.id}/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        row.refresh_from_db()

    def test_retire_shortens_active_row_and_sets_updated_by(self):
        row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("4.25"),
            valid_from=self.today - timedelta(days=10),
            valid_until=self.today + timedelta(days=10),
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(f"/api/v4/rates/import-cogs/{row.id}/retire/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row.refresh_from_db()
        self.assertEqual(row.valid_until, self.today - timedelta(days=1))
        self.assertEqual(row.updated_by, self.manager)

    def test_retire_deletes_future_row(self):
        row = ImportCOGS.objects.create(
            product_code=self.product_code,
            origin_airport="SYD",
            destination_airport="POM",
            carrier=self.carrier,
            currency="PGK",
            rate_per_shipment=Decimal("50.00"),
            valid_from=self.today + timedelta(days=5),
            valid_until=self.today + timedelta(days=15),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(f"/api/v4/rates/import-cogs/{row.id}/retire/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["deleted"])
        self.assertFalse(ImportCOGS.objects.filter(id=row.id).exists())
