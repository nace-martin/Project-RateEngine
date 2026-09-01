from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Country
from core.tests.helpers import create_location
from parties.models import Company, Contact
from pricing_v4.models import CanonicalChargeType, ProductCode, ProductCodeContextRule
from quotes.models import Quote
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SpotBusinessMovementResolutionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="spot-business-movement",
            password="x",
            role="sales",
            department="AIR",
        )
        customer = Company.objects.create(name="SPOT Movement Customer", is_customer=True)
        contact = Contact.objects.create(company=customer, first_name="SPOT", last_name="Movement")
        china = Country.objects.create(code="CN", name="China")
        png = Country.objects.create(code="PG", name="Papua New Guinea")
        self.can = create_location(code="CAN", name="Guangzhou", country=china)
        self.pom = create_location(code="POM", name="Port Moresby", country=png)
        self.lae = create_location(code="LAE", name="Lae", country=png)
        self.quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            origin_location=self.can,
            destination_location=self.lae,
            service_scope="D2D",
            incoterm="EXW",
            payment_term=Quote.PaymentTerm.COLLECT,
            commodity_code="GCR",
            output_currency="PGK",
            request_details_json={
                "dimensions": [{
                    "pieces": 1,
                    "length_cm": "100",
                    "width_cm": "100",
                    "height_cm": "60",
                    "gross_weight_kg": "100",
                    "package_type": "Pallet",
                }],
                "buy_currency": "USD",
            },
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v3/spot/envelopes/",
            {
                "quote_id": str(self.quote.id),
                "shipment_context": {},
                "charges": [],
                "trigger_code": "MISSING_SCOPE_RATES",
                "trigger_text": "Missing required rate components",
                "conditions": {"rate_validity_hours": 72},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.envelope = SpotPricingEnvelopeDB.objects.get(id=response.data["id"])

        self.canonical_type = CanonicalChargeType.objects.create(
            code="DESTINATION_HANDLING",
            name="Destination Handling",
            category="HANDLING",
            is_active=True,
        )
        self.domestic_product = ProductCode.objects.create(
            id=3199,
            code="DOM-DEST-HANDLING",
            description="Domestic Destination Handling",
            domain=ProductCode.DOMAIN_DOMESTIC,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=True,
            gst_rate="0.1000",
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code="4300",
            gl_cost_code="5300",
            default_unit=ProductCode.UNIT_SHIPMENT,
            is_active=True,
        )
        ProductCodeContextRule.objects.create(
            canonical_charge_type=self.canonical_type,
            product_code=self.domestic_product,
            product_code_domain=ProductCode.DOMAIN_DOMESTIC,
            leg_role="DOMESTIC_ON_FORWARDING",
            commercial_position="DESTINATION",
            transport_mode="DOMESTIC_AIR",
            operational_location="",
            calculation_basis="",
            service_scope="",
            priority=100,
            is_active=True,
            review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
            source=ProductCodeContextRule.RuleSource.ADMIN,
        )
        self.line = SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            code="DEST-HANDLING",
            description="Destination handling",
            amount="50.00",
            currency="PGK",
            unit=SPEChargeLineDB.Unit.FLAT,
            bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            canonical_charge_type=self.canonical_type,
            normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
            source_label="Destination handling",
            source_excerpt="Destination handling PGK 50",
            source_reference="agent-test",
            entered_by=self.user,
            entered_at=timezone.now(),
        )
        self.line.refresh_from_db()
        self.url = f"/api/v3/spot/envelopes/{self.envelope.id}/business-movements/"

    def test_multi_leg_charge_is_not_guessed_and_options_are_readable(self):
        self.assertIsNone(self.line.journey_leg_id)
        self.assertEqual(
            self.line.product_code_resolution_audit_json.get("status"),
            "LEG_ASSIGNMENT_REQUIRED",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        charge = next(item for item in response.data["charges"] if item["charge_line_id"] == str(self.line.id))
        self.assertIsNone(charge["assigned_leg_key"])
        self.assertEqual(len(charge["options"]), 2)
        self.assertEqual(
            [option["leg_key"] for option in charge["options"]],
            [
                "01:INTERNATIONAL_IMPORT:CAN:POM",
                "02:DOMESTIC_ON_FORWARDING:POM:LAE",
            ],
        )
        self.assertEqual(
            charge["options"][1]["label"],
            "Domestic On-forwarding: POM → LAE",
        )

    def test_operator_selects_business_movement_and_server_reruns_leg_aware_productcode(self):
        response = self.client.get(self.url)
        charge = next(item for item in response.data["charges"] if item["charge_line_id"] == str(self.line.id))

        applied = self.client.post(
            self.url,
            {
                "charge_line_id": str(self.line.id),
                "journey_revision": charge["journey_revision"],
                "leg_key": "02:DOMESTIC_ON_FORWARDING:POM:LAE",
            },
            format="json",
        )

        self.assertEqual(applied.status_code, status.HTTP_200_OK)
        self.assertEqual(applied.data["assigned_leg_key"], "02:DOMESTIC_ON_FORWARDING:POM:LAE")
        self.assertEqual(applied.data["product_code_domain"], "DOMESTIC")
        self.assertEqual(applied.data["product_code_resolution_status"], "ASSIGNED")

        self.line.refresh_from_db()
        self.assertEqual(self.line.journey_leg.leg_key, "02:DOMESTIC_ON_FORWARDING:POM:LAE")
        self.assertEqual(self.line.resolved_product_code_id, self.domestic_product.id)
        self.assertEqual(self.line.charge_context_json["product_code_domain"], "DOMESTIC")
        self.assertEqual(self.line.charge_context_json["leg_role"], "DOMESTIC_ON_FORWARDING")

        # A later non-route edit must preserve the explicit movement assignment.
        self.line.note = "Reviewed supplier note"
        self.line.save(update_fields=["note"])
        self.line.refresh_from_db()
        self.assertEqual(self.line.journey_leg.leg_key, "02:DOMESTIC_ON_FORWARDING:POM:LAE")

    def test_stale_journey_revision_fails_closed_without_mutating_line(self):
        response = self.client.post(
            self.url,
            {
                "charge_line_id": str(self.line.id),
                "journey_revision": 999,
                "leg_key": "02:DOMESTIC_ON_FORWARDING:POM:LAE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error_code"], "JOURNEY_REVISION_STALE")
        self.line.refresh_from_db()
        self.assertIsNone(self.line.journey_leg_id)
