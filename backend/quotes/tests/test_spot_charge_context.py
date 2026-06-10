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


class SpotChargeAmbiguityDocumentationTests(TestCase):
    """
    Phase 10.3c — SPOT Charge Ambiguity Documentation Tests
    
    This class contains test cases that serve as documentation for why the current alias-only
    mapping registry (`ChargeAlias`) is commercially insufficient for automated mapping.
    Different contexts (bucket/section, calculation basis, agent, route, etc.) can change
    the correct target ProductCode, even when the raw text label is identical.
    
    These tests demonstrate that the database can capture the distinct context metadata correctly
    without changing the current underlying resolution/alias logic, preserving the exact mapping
    behavior while identifying the need for future compound mapping rules or canonical charge types.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='ambiguity_analyst',
            email='ambiguity@rateengine.com',
            password='testpassword',
            role='sales'
        )
        
        # 1. Product Codes representing different fuel surcharge contexts
        cls.pc_airline_fuel = ProductCode.objects.create(
            id=3001,
            code='EXP-FSC-AIR',
            description='Airline Fuel Surcharge',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gl_revenue_code='4003',
            gl_cost_code='5003',
            default_unit=ProductCode.UNIT_KG,
        )
        cls.pc_cartage_fuel = ProductCode.objects.create(
            id=3002,
            code='EXP-FSC-PICKUP',
            description='Origin Cartage Fuel Surcharge',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gl_revenue_code='4004',
            gl_cost_code='5004',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

        # 2. Product Codes representing different handling contexts
        cls.pc_origin_handling = ProductCode.objects.create(
            id=3003,
            code='EXP-HANDLE-ORG',
            description='Origin Handling Fee',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gl_revenue_code='4005',
            gl_cost_code='5005',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.pc_dest_handling = ProductCode.objects.create(
            id=3004,
            code='EXP-HANDLE-DST',
            description='Destination Handling Fee',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gl_revenue_code='4006',
            gl_cost_code='5006',
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

        # 3. Create a single alias for 'FSC' mapping to Airline Fuel Surcharge.
        # This shows how an alias-only lookup resolves everything to one Code, regardless of context.
        cls.alias_fsc = ChargeAlias.objects.create(
            alias_text='fsc',
            normalized_alias_text='fsc',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=cls.pc_airline_fuel,
            priority=10,
        )

    def test_fsc_ambiguity_airfreight_vs_cartage(self):
        """
        Business Case 1: Raw label 'FSC' is ambiguous.
        
        - Under 'airfreight' bucket/section with 'per_kg' unit (calculation_basis), 'FSC' represents
          an Airline Fuel Surcharge (EXP-FSC-AIR).
        - Under 'origin_charges' bucket/section with percentage or flat basis, 'FSC' represents
          Origin Cartage Fuel Surcharge (EXP-FSC-PICKUP).
          
        This test documents that while both lines store their respective context metadata uniquely,
        the current resolver maps both to the same ProductCode (EXP-FSC-AIR) because of the alias text.
        This demonstrates the need for future context-aware mapping.
        """
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'service_scope': 'D2D',
                'agent_name': 'Singapore Cartage Ltd'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        # FSC under Airfreight (Airline Fuel Surcharge)
        air_charge = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_AIR',
                'description': 'FSC',
                'amount': Decimal('0.35'),
                'currency': 'SGD',
                'unit': 'per_kg',
                'bucket': 'airfreight',
                'source_reference': 'AIR-INV-01'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        # FSC under Origin Cartage (Cartage Fuel Surcharge)
        cartage_charge = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_CRT',
                'description': 'FSC',
                'amount': Decimal('45.00'),
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'CRT-INV-01'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        # Assert context metadata is successfully captured and preserved separately for both
        self.assertEqual(air_charge.bucket, 'airfreight')
        self.assertEqual(air_charge.calculation_basis, 'per_kg')
        
        self.assertEqual(cartage_charge.bucket, 'origin_charges')
        self.assertEqual(cartage_charge.calculation_basis, 'flat')

        # Document current mapping limitation: both resolve to the single exact alias's product code (Airline Fuel Surcharge)
        # In a future compound mapping system, cartage_charge would resolve to EXP-FSC-PICKUP instead.
        self.assertEqual(air_charge.resolved_product_code, self.pc_airline_fuel)
        self.assertEqual(cartage_charge.resolved_product_code, self.pc_airline_fuel)

    def test_handling_ambiguity_origin_vs_destination(self):
        """
        Business Case 2: Raw label 'Handling' is ambiguous.
        
        - Under 'origin_charges' bucket, 'Handling' represents Origin Handling (EXP-HANDLE-ORG).
        - Under 'destination_charges' bucket, 'Handling' represents Destination Handling (EXP-HANDLE-DST).
          
        This test documents that the database properly isolates the bucket/section metadata,
        laying the groundwork for future route/section-based mapping rules.
        """
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'service_scope': 'D2D'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        origin_handling = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'HANDLING_ORG',
                'description': 'Handling',
                'amount': Decimal('60.00'),
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'ORG-INV-99'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        dest_handling = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'HANDLING_DST',
                'description': 'Handling',
                'amount': Decimal('75.00'),
                'currency': 'PGK',
                'unit': 'flat',
                'bucket': 'destination_charges',
                'source_reference': 'DST-INV-99'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        # Assert context metadata isolates the bucket context
        self.assertEqual(origin_handling.bucket, 'origin_charges')
        self.assertEqual(dest_handling.bucket, 'destination_charges')

        # Since no alias is currently defined for 'Handling' in setup, both remain UNMAPPED for now.
        # This confirms that production mapping remains safe and unmodified in this slice.
        self.assertEqual(origin_handling.normalization_status, 'UNMAPPED')
        self.assertEqual(dest_handling.normalization_status, 'UNMAPPED')

    def test_reconciliation_safeguards_manual_resolutions(self):
        """
        Business Case 3: Manual override preservation during reconciliation.
        
        If an operator manually resolves an ambiguous/unmapped raw label (e.g. mapping cartage 'FSC' to EXP-FSC-PICKUP),
        the system's reconciliation logic MUST preserve this decision.
        Re-running mapping or updating values must not overwrite the user's manual selection.
        """
        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

        charge_data = {
            'code': 'FSC_CRT',
            'description': 'FSC',
            'amount': Decimal('45.00'),
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'CRT-INV-01'
        }

        # Create charge line (which will auto-map to EXP-FSC-AIR because of the exact alias registry)
        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.resolved_product_code, self.pc_airline_fuel)

        # User corrects this manually to the appropriate cartage fuel product code
        charge_line.manual_resolved_product_code = self.pc_cartage_fuel
        charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        charge_line.manual_resolution_by = self.user
        charge_line.manual_resolution_at = timezone.now()
        charge_line.save()

        # Simulate a reconciliation updates trigger calling _build_spe_charge_line_field_values
        fields = _build_spe_charge_line_field_values(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json,
            existing_line=charge_line
        )

        # Ensure the manual choice is preserved intact
        self.assertEqual(fields['manual_resolved_product_code'], self.pc_cartage_fuel)
        self.assertEqual(fields['manual_resolution_status'], SPEChargeLineDB.ManualResolutionStatus.RESOLVED)

