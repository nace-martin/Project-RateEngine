import uuid
from datetime import date, datetime
from decimal import Decimal

from core.dataclasses import LocationRef, Piece, QuoteInput, ShipmentDetails
from core.models import Location
from django.test import TestCase
from django.utils import timezone
from parties.models import Company, Contact

from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.services.commercial_policy import (
    MissingCommercialPolicyError,
    require_commercial_terms_policy,
    resolve_commercial_terms_policy,
)


class CommercialPolicyResolutionTests(TestCase):
    def setUp(self):
        # Clear policies to test deterministic resolution in isolation
        CommercialTermsPolicy.objects.all().delete()

        self.policy_2026 = CommercialTermsPolicy.objects.create(
            policy_code="POLICY-2026",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            target_gross_margin_percent=Decimal("20.00"),
            import_caf_percent=Decimal("5.00"),
            export_caf_percent=Decimal("10.00"),
            gst_standard_percent=Decimal("10.00"),
            is_active=True,
        )

    def test_property_rate_conversions(self):
        self.assertEqual(self.policy_2026.target_gross_margin_rate, Decimal("0.20"))
        self.assertEqual(self.policy_2026.import_caf_rate, Decimal("0.05"))
        self.assertEqual(self.policy_2026.export_caf_rate, Decimal("0.10"))
        self.assertEqual(self.policy_2026.gst_standard_rate, Decimal("0.10"))

    def test_resolve_within_date_window(self):
        resolved = resolve_commercial_terms_policy(date(2026, 6, 15))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.policy_code, "POLICY-2026")

    def test_resolve_with_string_date(self):
        resolved = resolve_commercial_terms_policy("2026-07-04")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.policy_code, "POLICY-2026")

    def test_resolve_with_datetime(self):
        dt = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.get_current_timezone())
        resolved = resolve_commercial_terms_policy(dt)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.policy_code, "POLICY-2026")

    def test_resolve_outside_date_window(self):
        resolved = resolve_commercial_terms_policy(date(2027, 2, 1))
        self.assertIsNone(resolved)

    def test_inactive_policy_not_resolved(self):
        self.policy_2026.is_active = False
        self.policy_2026.save()

        resolved = resolve_commercial_terms_policy(date(2026, 6, 1))
        self.assertIsNone(resolved)

    def test_require_policy_fails_closed(self):
        self.policy_2026.is_active = False
        self.policy_2026.save()

        with self.assertRaises(MissingCommercialPolicyError):
            require_commercial_terms_policy(date(2026, 6, 1))

    def test_multiple_policies_latest_valid_selected(self):
        CommercialTermsPolicy.objects.create(
            policy_code="POLICY-2027",
            valid_from=date(2027, 1, 1),
            valid_until=None,
            target_gross_margin_percent=Decimal("25.00"),
            import_caf_percent=Decimal("6.00"),
            export_caf_percent=Decimal("12.00"),
            gst_standard_percent=Decimal("10.00"),
            is_active=True,
        )

        resolved_2026 = resolve_commercial_terms_policy(date(2026, 6, 1))
        self.assertEqual(resolved_2026.policy_code, "POLICY-2026")

        resolved_2027 = resolve_commercial_terms_policy(date(2027, 3, 1))
        self.assertEqual(resolved_2027.policy_code, "POLICY-2027")


class AdapterCommercialPolicyCutoverTests(TestCase):
    def setUp(self):
        CommercialTermsPolicy.objects.all().delete()
        self.policy = CommercialTermsPolicy.objects.create(
            policy_code="LAUNCH-POLICY-2026",
            valid_from=date(2026, 1, 1),
            valid_until=None,
            target_gross_margin_percent=Decimal("20.00"),
            import_caf_percent=Decimal("5.00"),
            export_caf_percent=Decimal("10.00"),
            gst_standard_percent=Decimal("10.00"),
            is_active=True,
        )

        customer = Company.objects.first()
        contact = Contact.objects.filter(company=customer).first()
        self.customer_id = customer.id if customer else uuid.uuid4()
        self.contact_id = contact.id if contact else uuid.uuid4()

        pom = Location.objects.filter(code="POM").first()
        bne = Location.objects.filter(code="BNE").first()

        self.pom_ref = LocationRef(
            id=pom.id if pom else uuid.uuid4(),
            code="POM",
            name="Port Moresby",
            country_code="PG",
            currency_code="PGK",
        )
        self.bne_ref = LocationRef(
            id=bne.id if bne else uuid.uuid4(),
            code="BNE",
            name="Brisbane",
            country_code="AU",
            currency_code="AUD",
        )
        self.pieces = [
            Piece(
                pieces=1,
                length_cm=Decimal(50),
                width_cm=Decimal(50),
                height_cm=Decimal(50),
                gross_weight_kg=Decimal("100.0"),
            )
        ]

    def test_adapter_resolves_commercial_terms_policy(self):
        shipment = ShipmentDetails(
            origin_location=self.pom_ref,
            destination_location=self.bne_ref,
            service_scope="A2A",
            payment_term="PREPAID",
            incoterm="DAP",
            shipment_type="EXPORT",
            mode="AIR",
            pieces=self.pieces,
            is_dangerous_goods=False,
            commodity_code="GCR",
        )
        qi = QuoteInput(
            customer_id=self.customer_id,
            contact_id=self.contact_id,
            quote_date=date(2026, 6, 1),
            output_currency="PGK",
            shipment=shipment,
        )
        adapter = PricingServiceV4Adapter(qi)
        self.assertIsNotNone(adapter.get_commercial_terms_policy())
        self.assertEqual(adapter.get_commercial_terms_policy().policy_code, "LAUNCH-POLICY-2026")

    def test_export_fails_closed_when_commercial_policy_missing(self):
        # Delete active policy
        CommercialTermsPolicy.objects.all().delete()

        shipment = ShipmentDetails(
            origin_location=self.pom_ref,
            destination_location=self.bne_ref,
            service_scope="A2A",
            payment_term="PREPAID",
            incoterm="DAP",
            shipment_type="EXPORT",
            mode="AIR",
            pieces=self.pieces,
            is_dangerous_goods=False,
            commodity_code="GCR",
        )
        qi = QuoteInput(
            customer_id=self.customer_id,
            contact_id=self.contact_id,
            quote_date=date(2026, 6, 1),
            output_currency="PGK",
            shipment=shipment,
        )
        adapter = PricingServiceV4Adapter(qi)
        with self.assertRaises(MissingCommercialPolicyError):
            adapter.calculate_charges()

    def test_import_fails_closed_when_commercial_policy_missing(self):
        CommercialTermsPolicy.objects.all().delete()

        shipment = ShipmentDetails(
            origin_location=self.bne_ref,
            destination_location=self.pom_ref,
            service_scope="A2A",
            payment_term="COLLECT",
            incoterm="DAP",
            shipment_type="IMPORT",
            mode="AIR",
            pieces=self.pieces,
            is_dangerous_goods=False,
            commodity_code="GCR",
        )
        qi = QuoteInput(
            customer_id=self.customer_id,
            contact_id=self.contact_id,
            quote_date=date(2026, 6, 1),
            output_currency="PGK",
            shipment=shipment,
        )
        adapter = PricingServiceV4Adapter(qi)
        with self.assertRaises(MissingCommercialPolicyError):
            adapter.calculate_charges()
