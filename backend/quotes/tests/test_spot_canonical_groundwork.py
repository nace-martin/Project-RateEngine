from django.test import TestCase
from django.db import IntegrityError
from pricing_v4.models import ProductCode, ChargeAlias, CanonicalChargeType
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB
from quotes.services.charge_normalization import resolve_charge_alias


class SpotCanonicalGroundworkTests(TestCase):
    """
    Test suite for Phase 10.3e — CanonicalChargeType groundwork.
    Verifies that the new model, references, uniqueness, and seeded database taxonomy function correctly
    without modifying the legacy alias resolution or manual resolution workflows.
    """

    def test_canonical_charge_types_can_be_created(self):
        """Verify new CanonicalChargeType rows can be created successfully."""
        ct = CanonicalChargeType.objects.create(
            code='CUSTOM_TEST_CHARGE',
            name='Custom Test Charge',
            category='TEST',
            mode_scope='ANY',
            direction_scope='ANY',
            is_system=False,
            is_active=True,
            sort_order=500
        )
        self.assertIsNotNone(ct.pk)
        self.assertEqual(ct.code, 'CUSTOM_TEST_CHARGE')

    def test_seeded_taxonomy_exists(self):
        """Verify the 18 seeded taxonomy entries exist in the database."""
        expected_codes = {
            'AIR_FREIGHT', 'ORIGIN_HANDLING', 'ORIGIN_CARTAGE', 'DEST_HANDLING', 'DEST_DELIVERY',
            'CUSTOMS_CLEARANCE', 'QUARANTINE_INSP', 'AWB_DOCUMENTATION', 'ORIGIN_DOCS', 'DEST_DOCS',
            'SECURITY_SCREENING', 'AIRLINE_FUEL', 'CARTAGE_FUEL', 'WAR_RISK', 'ADMIN_COMMUNICATION',
            'UNKNOWN_CHARGE', 'CONDITIONAL_STORAGE', 'CONDITIONAL_DEMURRAGE'
        }
        actual_codes = set(CanonicalChargeType.objects.filter(is_system=True).values_list('code', flat=True))
        
        # Ensure all expected codes are present in the seeded taxonomy
        self.assertTrue(expected_codes.issubset(actual_codes))

    def test_canonical_codes_are_unique(self):
        """Verify unique code constraint on CanonicalChargeType."""
        CanonicalChargeType.objects.create(
            code='UNIQUE_CODE_A',
            name='Unique A',
            category='TEST'
        )
        with self.assertRaises(IntegrityError):
            CanonicalChargeType.objects.create(
                code='UNIQUE_CODE_A',
                name='Duplicate code A',
                category='TEST'
            )

    def test_inactive_types_can_exist_but_are_not_returned_by_active_helper(self):
        """Verify inactive CanonicalChargeType records can exist and are filtered by active queries."""
        ct_active = CanonicalChargeType.objects.create(
            code='TEST_ACTIVE',
            name='Test Active',
            category='TEST',
            is_active=True
        )
        ct_inactive = CanonicalChargeType.objects.create(
            code='TEST_INACTIVE',
            name='Test Inactive',
            category='TEST',
            is_active=False
        )

        active_types = list(CanonicalChargeType.objects.filter(is_active=True))
        self.assertIn(ct_active, active_types)
        self.assertNotIn(ct_inactive, active_types)

    def test_legacy_alias_to_product_code_resolution_remains_unchanged(self):
        """Verify legacy alias normalization maps directly to ProductCode, ignoring canonical mapping for now."""
        # Create a test ProductCode
        pc = ProductCode.objects.create(
            id=2990,
            code='EXP-TEST-PC',
            description='Export Test Product Code',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
        )

        # Create a test CanonicalChargeType
        ct = CanonicalChargeType.objects.create(
            code='TEST_CANONICAL_TYPE',
            name='Test Canonical Type',
            category='TEST'
        )

        # Create a ChargeAlias pointing directly to pc, but also linking the canonical type
        alias = ChargeAlias.objects.create(
            alias_text='test raw surcharge label',
            normalized_alias_text='test raw surcharge label',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=pc,
            canonical_charge_type=ct,
            priority=5,
        )

        # Execute resolution
        result = resolve_charge_alias(
            'test raw surcharge label',
            mode_scope='EXPORT',
            direction_scope='ORIGIN'
        )

        # Ensure the deterministic output is still matched and points directly to the product code
        self.assertEqual(result.normalization_status, 'MATCHED')
        self.assertEqual(result.resolved_product_code, pc)
        self.assertEqual(result.resolved_charge_alias, alias)
        self.assertEqual(result.resolved_charge_alias.canonical_charge_type, ct)


class SpotCanonicalAssignmentTests(TestCase):
    """
    Test suite for Phase 10.3f — Canonical Assignment Metadata.
    Verifies that SPEChargeLineDB.canonical_charge_type is populated during normalization and reconciliation.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='assignment_analyst',
            email='assignment@rateengine.com',
            password='testpassword',
            role='sales'
        )
        cls.pc = ProductCode.objects.create(
            id=2991,
            code='EXP-TEST-FSC',
            description='Export Fuel Surcharge',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
        )
        cls.ct = CanonicalChargeType.objects.create(
            code='AIRLINE_FUEL_TEST',
            name='Airline Fuel Surcharge (Test)',
            category='FUEL'
        )
        cls.alias_with_ct = ChargeAlias.objects.create(
            alias_text='fsc label with ct',
            normalized_alias_text='fsc label with ct',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=cls.pc,
            canonical_charge_type=cls.ct,
            priority=5,
        )
        cls.alias_without_ct = ChargeAlias.objects.create(
            alias_text='fsc label without ct',
            normalized_alias_text='fsc label without ct',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=cls.pc,
            canonical_charge_type=None,
            priority=5,
        )

    def _create_spe(self):
        from django.utils import timezone
        return SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': 'SIN',
                'destination_code': 'POM',
                'origin_country': 'SG',
                'destination_country': 'PG',
                'service_scope': 'D2D'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

    def test_matched_alias_with_canonical_type_populates_spe_canonical_charge_type(self):
        """Verify matched alias with canonical type populates SPEChargeLineDB.canonical_charge_type."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()
        
        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_LINE',
                'description': 'fsc label with ct',
                'amount': 50.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-1'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.canonical_charge_type, self.ct)
        self.assertEqual(charge_line.resolved_product_code, self.pc)

    def test_matched_alias_without_canonical_type_leaves_field_null(self):
        """Verify matched alias without canonical type leaves SPEChargeLineDB.canonical_charge_type null."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'FSC_LINE_NO_CT',
                'description': 'fsc label without ct',
                'amount': 50.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-2'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertIsNone(charge_line.canonical_charge_type)
        self.assertEqual(charge_line.resolved_product_code, self.pc)

    def test_reconciliation_preserves_manual_product_code_resolution(self):
        """Verify reconciliation preserves manual resolved product code and status."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line, _build_spe_charge_line_field_values
        spe = self._create_spe()
        
        charge_data = {
            'code': 'FSC_LINE',
            'description': 'fsc label with ct',
            'amount': 50.00,
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'REF-1'
        }

        # Create line
        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )

        # Apply manual resolution
        dummy_pc = ProductCode.objects.create(
            id=2992,
            code='EXP-MANUAL-PC',
            description='Export Manual Product Code',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
        )
        charge_line.manual_resolved_product_code = dummy_pc
        charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        charge_line.manual_resolution_by = self.user
        charge_line.manual_resolution_at = timezone.now()
        charge_line.save()

        # Reconcile / rebuild fields
        fields = _build_spe_charge_line_field_values(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json,
            existing_line=charge_line
        )

        # Check manual resolution is kept
        self.assertEqual(fields['manual_resolved_product_code'], dummy_pc)
        self.assertEqual(fields['manual_resolution_status'], SPEChargeLineDB.ManualResolutionStatus.RESOLVED)

    def test_reconciliation_preserves_existing_canonical_charge_type_if_no_matched_alias(self):
        """Verify reconciliation preserves existing canonical_charge_type if matched alias has no canonical type."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line, _build_spe_charge_line_field_values
        spe = self._create_spe()

        # Line initially created with ct
        charge_data = {
            'code': 'FSC_LINE',
            'description': 'fsc label with ct',
            'amount': 50.00,
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'REF-1'
        }

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.canonical_charge_type, self.ct)

        # Reconcile with updated description that does not map to any alias with a canonical type
        updated_charge_data = charge_data.copy()
        updated_charge_data['description'] = 'fsc label without ct' # maps to alias_without_ct (no canonical type)

        fields = _build_spe_charge_line_field_values(
            spe_db=spe,
            charge=updated_charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json,
            existing_line=charge_line
        )

        # Ensure the existing canonical type is preserved unchanged
        self.assertEqual(fields['canonical_charge_type'], self.ct)

