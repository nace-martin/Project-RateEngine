from datetime import timedelta
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
from quotes.models import Quote
from quotes.services.draft_quote_review_service import unresolved_blockers
from quotes.services.spot_pricing_identity import (
    PRICING_IDENTITY_VERSION,
    SPOT_PRICING_IDENTITY_DUPLICATE,
    SPOT_PRICING_IDENTITY_STALE_CONTEXT,
    pricing_identity_review_blockers,
    resolve_spot_pricing_identity,
)
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class SpotPricingIdentityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="spot-pricing-identity",
            password="x",
            role="sales",
            department="AIR",
        )
        customer = Company.objects.create(name="SPOT Pricing Identity", is_customer=True)
        contact = Contact.objects.create(company=customer, first_name="SPOT", last_name="Identity")
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

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.post(
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
            code="AIR_FREIGHT_PRICING_IDENTITY",
            name="Air Freight Pricing Identity",
            category="FREIGHT",
            is_active=True,
        )
        self.product = ProductCode.objects.create(
            id=2198,
            code="IMP-AIR-FRT-IDENTITY",
            description="Import Air Freight Identity",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_rate="0.0000",
            gst_treatment=ProductCode.GST_TREATMENT_EXEMPT,
            gl_revenue_code="4198",
            gl_cost_code="5198",
            default_unit=ProductCode.UNIT_KG,
            is_active=True,
        )
        ProductCodeContextRule.objects.create(
            canonical_charge_type=self.canonical_type,
            product_code=self.product,
            product_code_domain=ProductCode.DOMAIN_IMPORT,
            leg_role=LegRole.INTERNATIONAL_IMPORT.value,
            commercial_position=CommercialPosition.FREIGHT.value,
            transport_mode=TransportMode.INTERNATIONAL_AIR.value,
            priority=100,
            is_active=True,
            review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
            source=ProductCodeContextRule.RuleSource.ADMIN,
        )

    def _create_resolved_line(self, *, currency="USD", description="Air Freight"):
        line = SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            code="AIRFREIGHT_SPOT",
            description=description,
            amount="5.00",
            currency=currency,
            unit=SPEChargeLineDB.Unit.PER_KG,
            bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
            is_primary_cost=True,
            canonical_charge_type=self.canonical_type,
            calculation_basis="per_kg",
            normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
            normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
            source_reference="agent quote",
            entered_by=self.user,
            entered_at=timezone.now(),
        )
        line.refresh_from_db()
        return line

    def test_resolved_live_charge_derives_architecture_pricing_identity(self):
        line = self._create_resolved_line()

        resolution = resolve_spot_pricing_identity(line)

        self.assertTrue(resolution.applicable)
        self.assertTrue(resolution.ready)
        self.assertEqual(resolution.blocker_codes, ())
        identity = resolution.identity
        self.assertIsNotNone(identity)
        self.assertEqual(identity.journey_revision, 1)
        self.assertEqual(identity.leg_key, "01:INTERNATIONAL_IMPORT:CAN:POM")
        self.assertEqual(identity.product_code, self.product.code)
        self.assertEqual(identity.commercial_position, "FREIGHT")
        self.assertEqual(identity.component, "FREIGHT")
        self.assertEqual(identity.currency, "USD")
        self.assertEqual(identity.product_code_domain, ProductCode.DOMAIN_IMPORT)
        self.assertEqual(identity.to_dict()["identity_version"], PRICING_IDENTITY_VERSION)
        self.assertEqual(
            identity.key,
            (
                1,
                "01:INTERNATIONAL_IMPORT:CAN:POM",
                self.product.code,
                "FREIGHT",
                "FREIGHT",
                "USD",
            ),
        )

    def test_duplicate_trusted_pricing_identity_blocks_draft_review(self):
        first = self._create_resolved_line(description="Air Freight supplier line 1")
        second = self._create_resolved_line(description="Air Freight supplier line 2")

        blockers = unresolved_blockers(self.envelope, SimpleNamespace(review_queue=[]))

        duplicate = next(item for item in blockers if item["code"] == SPOT_PRICING_IDENTITY_DUPLICATE)
        self.assertEqual(set(duplicate["charge_line_ids"]), {str(first.id), str(second.id)})
        self.assertEqual(
            duplicate["pricing_identity"]["leg_key"],
            "01:INTERNATIONAL_IMPORT:CAN:POM",
        )
        self.assertEqual(duplicate["pricing_identity"]["product_code"], self.product.code)
        self.assertFalse(
            any(item["code"] == "PRODUCTCODE_LEG_CONTEXT_UNRESOLVED" for item in blockers)
        )

    def test_currency_is_part_of_identity_so_distinct_supplier_currencies_do_not_collide(self):
        self._create_resolved_line(currency="USD", description="USD Air Freight")
        self._create_resolved_line(currency="AUD", description="AUD Air Freight")

        blockers = pricing_identity_review_blockers(self.envelope)

        self.assertFalse(any(item["code"] == SPOT_PRICING_IDENTITY_DUPLICATE for item in blockers))

    def test_stale_charge_context_fails_closed_and_blocks_review(self):
        line = self._create_resolved_line()
        stale_context = dict(line.charge_context_json)
        stale_context["leg_key"] = "99:DOMESTIC_ON_FORWARDING:POM:LAE"
        SPEChargeLineDB.objects.filter(pk=line.pk).update(charge_context_json=stale_context)
        line.refresh_from_db()

        resolution = resolve_spot_pricing_identity(line)
        blockers = unresolved_blockers(self.envelope, SimpleNamespace(review_queue=[]))

        self.assertFalse(resolution.ready)
        self.assertIn(SPOT_PRICING_IDENTITY_STALE_CONTEXT, resolution.blocker_codes)
        self.assertTrue(
            any(
                item["code"] == SPOT_PRICING_IDENTITY_STALE_CONTEXT
                and item["charge_line_id"] == str(line.id)
                for item in blockers
            )
        )

    def test_non_phase16_legacy_line_does_not_gain_new_identity_blockers(self):
        legacy_envelope = SpotPricingEnvelopeDB.objects.create(
            status="draft",
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "SG",
                "origin_code": "POM",
                "destination_code": "SIN",
                "commodity": "GCR",
                "total_weight_kg": 100,
                "pieces": 1,
                "service_scope": "p2p",
            },
            conditions_json={},
            spot_trigger_reason_code="LEGACY_TEST",
            spot_trigger_reason_text="Legacy test",
            created_by=self.user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        line = SPEChargeLineDB.objects.create(
            envelope=legacy_envelope,
            code="AIRFREIGHT_SPOT",
            description="Legacy Air Freight",
            amount="5.00",
            currency="USD",
            unit=SPEChargeLineDB.Unit.PER_KG,
            bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
            is_primary_cost=True,
            source_reference="legacy",
            entered_by=self.user,
            entered_at=timezone.now(),
        )

        resolution = resolve_spot_pricing_identity(line)

        self.assertFalse(resolution.applicable)
        self.assertFalse(resolution.ready)
        self.assertEqual(resolution.blocker_codes, ())
        self.assertEqual(pricing_identity_review_blockers(legacy_envelope), [])
