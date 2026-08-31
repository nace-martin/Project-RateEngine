from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Country
from core.tests.helpers import create_location
from parties.models import Company, Contact
from pricing_v4.contracts.charge_context import CommercialPosition, LegRole, TransportMode
from pricing_v4.models import CanonicalChargeType, ProductCode, ProductCodeContextRule
from quotes.models import Quote, ShipmentJourneyDB
from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.draft_quote_review_service import unresolved_blockers
from quotes.services.spot_quote_context import build_trusted_quote_context
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SpotJourneyContractBaselineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="spot-journey-baseline",
            password="x",
            role="sales",
            department="AIR",
        )
        customer = Company.objects.create(name="SPOT Journey Baseline", is_customer=True)
        contact = Contact.objects.create(company=customer, first_name="SPOT", last_name="Owner")
        china = Country.objects.create(code="CN", name="China")
        png = Country.objects.create(code="PG", name="Papua New Guinea")
        self.can = create_location(code="CAN", name="Guangzhou", country=china)
        self.pom = create_location(code="POM", name="Port Moresby", country=png)
        self.quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            origin_location=self.can,
            destination_location=self.pom,
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

    def _create_live_envelope(self, charges=None):
        client = APIClient()
        client.force_authenticate(user=self.user)
        payload = {
            "quote_id": str(self.quote.id),
            "shipment_context": {},
            "charges": charges or [],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }
        response = client.post("/api/v3/spot/envelopes/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return SpotPricingEnvelopeDB.objects.get(id=response.data["id"])

    def test_trusted_spot_snapshot_is_directly_plannable_without_client_reconstruction(self):
        context, missing = build_trusted_quote_context(self.quote)

        self.assertEqual(missing, [])
        self.assertEqual(context["service_domain"], "AIR")
        self.assertEqual(context["quote_date"], self.quote.created_at.date().isoformat())
        self.assertEqual(context["chargeable_weight_kg"], 100.0)
        self.assertTrue(context["pickup_requested"])
        self.assertTrue(context["delivery_requested"])

        plan = AirJourneyPlanner().plan(context)

        self.assertEqual(plan.status.value, "PLANNED")
        self.assertEqual(plan.pattern.value, "IMP_POM")
        self.assertEqual(plan.blockers, [])
        self.assertEqual(
            [leg.leg_key for leg in plan.legs],
            ["01:INTERNATIONAL_IMPORT:CAN:POM"],
        )

    def test_service_scope_changes_pickup_delivery_flags_without_guessing(self):
        expectations = {
            "A2A": (False, False),
            "D2A": (True, False),
            "A2D": (False, True),
            "D2D": (True, True),
        }
        for scope, expected in expectations.items():
            with self.subTest(scope=scope):
                self.quote.service_scope = scope
                self.quote.save(update_fields=["service_scope", "updated_at"])
                context, missing = build_trusted_quote_context(self.quote)
                self.assertEqual(missing, [])
                self.assertEqual(
                    (context["pickup_requested"], context["delivery_requested"]),
                    expected,
                )

    def test_live_quote_linked_spot_creation_persists_one_dark_mode_journey(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        payload = {
            "quote_id": str(self.quote.id),
            "shipment_context": {},
            "charges": [],
            "trigger_code": "MISSING_SCOPE_RATES",
            "trigger_text": "Missing required rate components",
            "conditions": {"rate_validity_hours": 72},
        }

        first = client.post("/api/v3/spot/envelopes/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        envelope = SpotPricingEnvelopeDB.objects.get(id=first.data["id"])
        journeys = ShipmentJourneyDB.objects.filter(spot_envelope=envelope)
        self.assertEqual(journeys.count(), 1)

        journey = journeys.get()
        self.assertEqual(journey.quote_id, self.quote.id)
        self.assertEqual(journey.pattern, "IMP_POM")
        self.assertEqual(journey.status, ShipmentJourneyDB.Status.NEEDS_REVIEW)
        self.assertIn("ROUTE_AUTOMATION_DISABLED", journey.blockers_json)
        self.assertEqual(
            list(journey.legs.values_list("leg_key", flat=True)),
            ["01:INTERNATIONAL_IMPORT:CAN:POM"],
        )
        self.assertEqual(self.quote.versions.count(), 0)
        self.assertEqual(envelope.charge_lines.count(), 0)

        retry = client.post("/api/v3/spot/envelopes/", payload, format="json")
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data["id"], first.data["id"])
        self.assertEqual(ShipmentJourneyDB.objects.filter(spot_envelope=envelope).count(), 1)
        self.assertEqual(journey.legs.count(), 1)

    def test_live_spot_charge_gets_trusted_leg_and_unresolved_productcode_blocks_review(self):
        envelope = self._create_live_envelope([
            {
                "code": "AIRFREIGHT_SPOT",
                "description": "Air Freight",
                "amount": "5.00",
                "currency": "USD",
                "unit": "per_kg",
                "bucket": "airfreight",
                "is_primary_cost": True,
                "source_reference": "agent quote",
            }
        ])

        line = envelope.charge_lines.get()
        self.assertIsNotNone(line.journey_leg_id)
        self.assertEqual(line.journey_leg.leg_key, "01:INTERNATIONAL_IMPORT:CAN:POM")
        self.assertEqual(line.charge_context_json["product_code_domain"], "IMPORT")
        self.assertEqual(line.charge_context_json["commercial_position"], "FREIGHT")
        self.assertEqual(line.product_code_resolution_audit_json["status"], "CONTEXT_INCOMPLETE")
        self.assertTrue(line.product_code_resolution_audit_json["phase_16_live"])

        blockers = unresolved_blockers(envelope, SimpleNamespace(review_queue=[]))
        self.assertTrue(any(item["code"] == "PRODUCTCODE_LEG_CONTEXT_UNRESOLVED" for item in blockers))

    def test_live_spot_charge_uses_leg_aware_rule_when_context_is_complete(self):
        envelope = self._create_live_envelope()
        canonical = CanonicalChargeType.objects.create(
            code="AIR_FREIGHT_BASELINE",
            name="Air Freight Baseline",
            category="FREIGHT",
            is_active=True,
        )
        product = ProductCode.objects.create(
            id=2197,
            code="IMP-AIR-FRT-BASELINE",
            description="Import Air Freight Baseline",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate="0.1000",
            gst_treatment=ProductCode.GST_TREATMENT_STANDARD,
            gl_revenue_code="4197",
            gl_cost_code="5197",
            default_unit=ProductCode.UNIT_SHIPMENT,
            is_active=True,
        )
        ProductCodeContextRule.objects.create(
            canonical_charge_type=canonical,
            product_code=product,
            product_code_domain=ProductCode.DOMAIN_IMPORT,
            leg_role=LegRole.INTERNATIONAL_IMPORT.value,
            commercial_position=CommercialPosition.FREIGHT.value,
            transport_mode=TransportMode.INTERNATIONAL_AIR.value,
            priority=100,
            is_active=True,
            review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
            source=ProductCodeContextRule.RuleSource.ADMIN,
        )

        line = SPEChargeLineDB.objects.create(
            envelope=envelope,
            code="AIRFREIGHT_SPOT",
            description="Air Freight",
            amount="5.00",
            currency="USD",
            unit=SPEChargeLineDB.Unit.PER_KG,
            bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
            is_primary_cost=True,
            canonical_charge_type=canonical,
            calculation_basis="per_kg",
            source_reference="agent quote",
            entered_by=self.user,
            entered_at=timezone.now(),
        )
        line.refresh_from_db()

        self.assertEqual(line.journey_leg.leg_key, "01:INTERNATIONAL_IMPORT:CAN:POM")
        self.assertEqual(line.resolved_product_code_id, product.id)
        self.assertEqual(line.product_code_resolution_audit_json["status"], "ASSIGNED")
        self.assertEqual(
            line.product_code_resolution_audit_json["selected_product_code"],
            product.code,
        )
        blockers = unresolved_blockers(envelope, SimpleNamespace(review_queue=[]))
        self.assertFalse(any(item["charge_line_id"] == str(line.id) for item in blockers))
