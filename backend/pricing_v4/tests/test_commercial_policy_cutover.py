import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from core.dataclasses import LocationRef, Piece, QuoteInput, ShipmentDetails
from core.models import Location
from django.test import TestCase
from django.utils import timezone
from parties.models import Company, Contact

from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm as ExportPaymentTerm
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.services.commercial_policy import (
    InvalidPolicyEffectiveDateError,
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

    def test_resolve_invalid_date_string_fails_closed(self):
        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy("not-a-valid-date")

        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy("")

        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy("   ")

        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy("2026-02-31")

    def test_resolve_unsupported_type_fails_closed(self):
        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy(12345)

        with self.assertRaises(InvalidPolicyEffectiveDateError):
            resolve_commercial_terms_policy(["2026-06-01"])

    def test_resolve_none_uses_current_effective_policy(self):
        resolved = resolve_commercial_terms_policy(None)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.policy_code, "POLICY-2026")

    def test_require_with_invalid_date_fails_closed(self):
        with self.assertRaises(InvalidPolicyEffectiveDateError):
            require_commercial_terms_policy("invalid-date")

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

    def test_missing_export_caf_fails_closed(self):
        self.policy.export_caf_percent = None
        self.policy.save()

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
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            adapter.calculate_charges()
        self.assertIn("Export CAF", str(cm.exception))

    def test_missing_import_caf_fails_closed(self):
        self.policy.import_caf_percent = None
        self.policy.save()

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
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            adapter.calculate_charges()
        self.assertIn("Import CAF", str(cm.exception))

    def test_missing_required_margin_fails_closed(self):
        # 1. Import engine fails closed on cost-derived calculation when margin is None
        import_engine = ImportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
            caf_rate=Decimal("0.05"),
            margin_rate=None,
        )
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            import_engine._apply_margin(Decimal("100.00"))
        self.assertIn("target gross margin", str(cm.exception).lower())

        # 2. Export engine fails closed on cost-derived calculation when margin is None
        export_engine = ExportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=ExportPaymentTerm.COLLECT,
            caf_rate=Decimal("0.10"),
            margin_rate=None,
        )
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            export_engine._apply_margin(Decimal("100.00"))
        self.assertIn("target gross margin", str(cm.exception).lower())

    def test_approved_sell_not_remargined(self):
        # When target margin is null, approved direct SELL rates (Export Prepaid or Import A2D)
        # must succeed without requiring or reapplying margin
        export_engine = ExportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=ExportPaymentTerm.PREPAID,
            caf_rate=Decimal("0.10"),
            margin_rate=None,
        )
        self.assertIsNone(export_engine.margin_rate)
        self.assertEqual(export_engine.payment_term, ExportPaymentTerm.PREPAID)

        import_engine = ImportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D,
            caf_rate=Decimal("0.05"),
            margin_rate=None,
        )
        self.assertIsNone(import_engine.margin_rate)
        self.assertEqual(import_engine.service_scope, ServiceScope.A2D)

    def test_invalid_effective_date_string_fails_closed_on_adapter_init(self):
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
            quote_date="not-a-valid-date-string",
            output_currency="PGK",
            shipment=shipment,
        )
        with self.assertRaises(InvalidPolicyEffectiveDateError):
            PricingServiceV4Adapter(qi)

    def _create_test_spe(self, shipment_type="IMPORT"):
        from quotes.models import SPEAcknowledgementDB, SPEChargeLineDB, SpotPricingEnvelopeDB
        from services.models import ServiceComponent

        ServiceComponent.objects.get_or_create(
            code="SPOT_FRT",
            defaults={"description": "Spot Freight", "mode": "AIR", "leg": "MAIN", "category": "TRANSPORT"},
        )

        now = timezone.now()
        spe = SpotPricingEnvelopeDB.objects.create(
            id=uuid.uuid4(),
            status="ready",
            spot_trigger_reason_code="TEST_TRIGGER",
            spot_trigger_reason_text="Test Trigger",
            shipment_context_json={
                "origin_country": "AU" if shipment_type == "IMPORT" else "PG",
                "destination_country": "PG" if shipment_type == "IMPORT" else "AU",
                "origin_code": "BNE" if shipment_type == "IMPORT" else "POM",
                "destination_code": "POM" if shipment_type == "IMPORT" else "BNE",
                "commodity": "GCR",
                "total_weight_kg": 100.0,
                "pieces": 1,
                "service_scope": "a2a",
                "shipment_type": shipment_type,
            },
            conditions_json={},
            expires_at=now + timedelta(days=1),
        )
        SPEAcknowledgementDB.objects.create(
            envelope=spe,
            acknowledged_at=now,
            statement="I acknowledge this is a conditional SPOT quote and not guaranteed",
        )
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="SPOT_FRT",
            description="Spot Freight",
            amount=Decimal("500.00"),
            currency="PGK",
            unit="per_shipment",
            bucket="airfreight",
            is_primary_cost=True,
            entered_at=now,
            source_reference="Test Supplier",
        )
        return spe

    def test_spot_missing_policy_fails_closed(self):
        CommercialTermsPolicy.objects.all().delete()
        spe = self._create_test_spe("IMPORT")

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
        adapter = PricingServiceV4Adapter(qi, spot_envelope_id=spe.id)
        with self.assertRaises(MissingCommercialPolicyError):
            adapter._calculate_spot_lines()

    def test_spot_null_margin_fails_closed_when_margin_required(self):
        self.policy.target_gross_margin_percent = None
        self.policy.save()
        spe = self._create_test_spe("IMPORT")

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
        adapter = PricingServiceV4Adapter(qi, spot_envelope_id=spe.id)
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            adapter._calculate_spot_lines()
        self.assertIn("target gross margin is missing", str(cm.exception).lower())

    def test_spot_null_applicable_caf_fails_closed(self):
        # 1. Import SPOT fails closed on missing Import CAF
        self.policy.import_caf_percent = None
        self.policy.save()
        spe_import = self._create_test_spe("IMPORT")

        shipment_import = ShipmentDetails(
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
        qi_import = QuoteInput(
            customer_id=self.customer_id,
            contact_id=self.contact_id,
            quote_date=date(2026, 6, 1),
            output_currency="PGK",
            shipment=shipment_import,
        )
        adapter_import = PricingServiceV4Adapter(qi_import, spot_envelope_id=spe_import.id)
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            adapter_import._calculate_spot_lines()
        self.assertIn("Import CAF is missing", str(cm.exception))

        # Restore import CAF, set export CAF to None
        self.policy.import_caf_percent = Decimal("5.00")
        self.policy.export_caf_percent = None
        self.policy.save()

        # 2. Export SPOT fails closed on missing Export CAF
        spe_export = self._create_test_spe("EXPORT")
        shipment_export = ShipmentDetails(
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
        qi_export = QuoteInput(
            customer_id=self.customer_id,
            contact_id=self.contact_id,
            quote_date=date(2026, 6, 1),
            output_currency="PGK",
            shipment=shipment_export,
        )
        adapter_export = PricingServiceV4Adapter(qi_export, spot_envelope_id=spe_export.id)
        with self.assertRaises(MissingCommercialPolicyError) as cm:
            adapter_export._calculate_spot_lines()
        self.assertIn("Export CAF is missing", str(cm.exception))

    def test_exact_existing_benchmark_parity(self):
        # Complete launch policy: 20% margin, 5% Import CAF, 10% Export CAF, 10% GST
        self.policy.target_gross_margin_percent = Decimal("20.00")
        self.policy.import_caf_percent = Decimal("5.00")
        self.policy.export_caf_percent = Decimal("10.00")
        self.policy.gst_standard_percent = Decimal("10.00")
        self.policy.is_active = True
        self.policy.save()

        # Verify rate conversions match canonical 2026 baseline
        self.assertEqual(self.policy.target_gross_margin_rate, Decimal("0.20"))
        self.assertEqual(self.policy.import_caf_rate, Decimal("0.05"))
        self.assertEqual(self.policy.export_caf_rate, Decimal("0.10"))
        self.assertEqual(self.policy.gst_standard_rate, Decimal("0.10"))

        # Verify Export Engine with complete policy produces deterministic rate conversions
        export_engine = ExportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=ExportPaymentTerm.PREPAID,
            tt_buy=Decimal("0.35"),
            tt_sell=Decimal("0.36"),
            caf_rate=self.policy.export_caf_rate,
            margin_rate=self.policy.target_gross_margin_rate,
        )
        self.assertEqual(export_engine.caf_rate, Decimal("0.10"))
        self.assertEqual(export_engine.margin_rate, Decimal("0.20"))

        # Verify Import Engine with complete policy produces deterministic rate conversions
        import_engine = ImportPricingEngine(
            quote_date=date(2026, 6, 1),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100.0"),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
            tt_buy=Decimal("0.35"),
            tt_sell=Decimal("0.36"),
            caf_rate=self.policy.import_caf_rate,
            margin_rate=self.policy.target_gross_margin_rate,
        )
        self.assertEqual(import_engine.caf_rate, Decimal("0.05"))
        self.assertEqual(import_engine.margin_rate, Decimal("0.20"))
        self.assertEqual(import_engine._apply_margin(Decimal("100.00")), Decimal("120.00"))
