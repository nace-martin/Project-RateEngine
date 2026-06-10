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
