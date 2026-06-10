from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from quotes.spot_models import SpotPricingEnvelopeDB, SPESourceBatchDB, SPEChargeLineDB
from pricing_v4.models import ProductCode, ChargeAlias
from quotes.services.charge_normalization import resolve_charge_alias
from quotes.spot_views import _build_spe_charge_line_field_values, _create_spe_charge_line

User = get_user_model()

class SpotChargeContextMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='test_analyst',
            email='analyst@rateengine.com',
            password='testpassword',
            role='sales'
        )
        cls.pc_handling = ProductCode.objects.create(
            id=2970,
            code='EXP-HANDLING',
            description='Export Handling',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate='0.00',
            gl_revenue_code='4001',
            gl_cost_code='5001',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.pc_customs = ProductCode.objects.create(
            id=2971,
            code='EXP-CUSTOMS',
            description='Export Customs Clearance',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gl_revenue_code='4002',
            gl_cost_code='5002',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

        # Create exact alias
        cls.alias_exact = ChargeAlias.objects.create(
            alias_text='handling fee',
            normalized_alias_text='handling fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=cls.pc_handling,
            priority=10,
        )

    def test_existing_alias_matching_still_works(self):
        """Verify standard alias matching behaves unchanged."""
        result = resolve_charge_alias(
            'handling fee',
            mode_scope='IMPORT',
            direction_scope='ORIGIN'
        )
        self.assertEqual(result.normalization_status, 'MATCHED')
        self.assertEqual(result.resolved_product_code, self.pc_handling)

    def test_new_context_metadata_is_stored(self):
        """Verify context snapshots and inferred calculation basis are correctly saved."""
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'service_scope': 'D2D',
                'agent_name': 'Singapore Freight Co',
                'origin_country': 'SG',
                'destination_country': 'PG'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )
        batch = SPESourceBatchDB.objects.create(
            envelope=spe,
            label='SIN Terminal Invoice',
            source_kind=SPESourceBatchDB.SourceKind.AGENT
        )

        charge_data = {
            'code': 'HANDLING_CHARGE',
            'description': 'handling fee',
            'amount': Decimal('120.00'),
            'currency': 'SGD',
            'unit': 'per_kg',
            'bucket': 'origin_charges',
            'source_reference': 'INV-12345',
            'source_section_label': 'Origin Cartage Surcharges',
            'confidence': 0.925
        }

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json,
            source_batch=batch
        )

        self.assertEqual(charge_line.calculation_basis, 'per_kg')
        self.assertEqual(charge_line.service_scope_snapshot, 'D2D')
        self.assertEqual(charge_line.agent_name_snapshot, 'Singapore Freight Co')
        self.assertEqual(charge_line.origin_code_snapshot, 'SIN')
        self.assertEqual(charge_line.destination_code_snapshot, 'POM')
        self.assertEqual(charge_line.route_context, 'SIN-POM')
        self.assertEqual(charge_line.source_section_label, 'Origin Cartage Surcharges')
        self.assertEqual(charge_line.normalization_confidence, Decimal('0.9250'))

    def test_unmapped_charge_line_stores_review_reason(self):
        """Unmapped charge lines should capture a clear review reason and leave confidence null if absent."""
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'origin_country': 'SG',
                'destination_country': 'PG'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        charge_data = {
            'code': 'UNKNOWN_FEE',
            'description': 'random non-matching raw charge label',
            'amount': Decimal('50.00'),
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'INV-12345'
        }

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        self.assertEqual(charge_line.normalization_status, 'UNMAPPED')
        self.assertEqual(charge_line.normalization_review_reason, 'No active alias matching raw label found in registry.')
        self.assertIsNone(charge_line.normalization_confidence)

    def test_ambiguous_charge_line_stores_review_reason(self):
        """Ambiguous charge lines capture conflicting alias review reason."""
        # Create a second alias with same text/priority but different product code to create ambiguity
        ChargeAlias.objects.create(
            alias_text='handling fee',
            normalized_alias_text='handling fee',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.IMPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=self.pc_customs,
            priority=10,
        )

        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'origin_country': 'SG',
                'destination_country': 'PG'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        charge_data = {
            'code': 'HANDLING_FEE',
            'description': 'handling fee',
            'amount': Decimal('75.00'),
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'INV-12345'
        }

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        self.assertEqual(charge_line.normalization_status, 'AMBIGUOUS')
        self.assertEqual(charge_line.normalization_review_reason, 'Multiple active aliases matched raw label with conflicting product codes.')

    def test_manual_resolved_product_code_survives_reconciliation(self):
        """User manual selections must survive reconciliation updates."""
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'origin_country': 'SG',
                'destination_country': 'PG'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        charge_data = {
            'code': 'HANDLING_CHARGE',
            'description': 'unmapped fee',
            'amount': Decimal('100.00'),
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'INV-12345'
        }

        # Create initially unmapped line
        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.normalization_status, 'UNMAPPED')

        # Simulate user resolving it manually to pc_customs
        charge_line.manual_resolved_product_code = self.pc_customs
        charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        charge_line.manual_resolution_by = self.user
        charge_line.manual_resolution_at = timezone.now()
        charge_line.save()

        # Re-run reconciliation mapping
        fields = _build_spe_charge_line_field_values(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json,
            existing_line=charge_line
        )

        # Verify manual resolution remains intact
        self.assertEqual(fields['manual_resolved_product_code'], self.pc_customs)
        self.assertEqual(fields['manual_resolution_status'], SPEChargeLineDB.ManualResolutionStatus.RESOLVED)

    def test_same_raw_label_different_buckets_different_metadata(self):
        """Same label in different buckets can store different calculation_basis and metadata."""
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'origin_country': 'SG',
                'destination_country': 'PG'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        origin_charge = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_ORIGIN',
                'description': 'Fuel Surcharge',
                'amount': Decimal('25.00'),
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'INV-12345'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        freight_charge = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_FREIGHT',
                'description': 'Fuel Surcharge',
                'amount': Decimal('0.45'),
                'currency': 'SGD',
                'unit': 'per_kg',
                'bucket': 'airfreight',
                'source_reference': 'INV-12345'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        self.assertEqual(origin_charge.calculation_basis, 'flat')
        self.assertEqual(freight_charge.calculation_basis, 'per_kg')
