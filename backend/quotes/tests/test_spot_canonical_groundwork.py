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


class SpotCanonicalReviewStatesTests(TestCase):
    """
    Test suite for Phase 10.3g — Canonical Review States.
    Verifies that SPEChargeLineDB.normalization_review_reason is correctly populated based on mapping issues.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='review_analyst',
            email='review@rateengine.com',
            password='testpassword',
            role='sales'
        )
        cls.pc = ProductCode.objects.create(
            id=2993,
            code='EXP-TEST-FSC-REV',
            description='Export Fuel Surcharge (Review)',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
        )
        cls.pc_ambig = ProductCode.objects.create(
            id=2994,
            code='EXP-TEST-FSC-AMB',
            description='Export Fuel Surcharge (Ambig)',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
        )
        cls.ct_fuel = CanonicalChargeType.objects.create(
            code='AIRLINE_FUEL_TEST_REV',
            name='Airline Fuel Surcharge (Review)',
            category='FUEL'
        )
        cls.ct_conditional, _ = CanonicalChargeType.objects.get_or_create(
            code='CONDITIONAL_STORAGE',
            defaults={
                'name': 'Conditional Storage (Review)',
                'category': 'MISC'
            }
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

    def test_unmapped_with_no_canonical_type_produces_canonical_type_missing(self):
        """Verify unmapped raw label with no canonical type maps to canonical_type_missing review reason."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'UNMAPPED_LINE',
                'description': 'completely unknown raw charge label here',
                'amount': 50.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-REV-1'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.normalization_status, 'UNMAPPED')
        self.assertEqual(charge_line.normalization_review_reason, 'canonical_type_missing')

    def test_canonical_type_exists_but_product_code_missing_produces_product_code_missing(self):
        """Verify canonical type with no ProductCode mapping produces product_code_missing review reason."""
        # Create an alias that maps to a CanonicalChargeType, but maps to NULL product_code?
        # Wait, our database integrity / validation might require product_code on ChargeAlias.
        # But wait! If we have a CanonicalChargeType matched via alias, but the resolved_product_code is null on the charge line
        # e.g., if the matched alias specifies canonical_charge_type but has product_code null (if nullable), or if we mock it.
        # Wait, resolved_product_code is returned byresolve_charge_alias. If resolve_charge_alias resolves to an alias, it returns its product_code.
        # But if the alias exists but is not mapped for this mode/scope in the future (where alias is mapped to canonical only, and mapping context resolves ProductCode),
        # then resolved_product_code can be null.
        # Let's mock a case where we create a ChargeAlias with product_code pointing to a dummy, but we simulate a null resolved_product_code.
        # Actually, let's look at _resolve_spe_charge_normalization_fields:
        # "resolved_product_code": normalization_result.resolved_product_code
        # Let's temporarily mock the resolved_product_code to None to trigger "product_code_missing".
        # Let's see: we can create a test case that directly exercises _resolve_spe_charge_normalization_fields or _build_spe_charge_line_field_values,
        # or we can create a ChargeAlias with a CanonicalChargeType, but where resolving it does not return a ProductCode (if we manually test the view helper).
        # Let's do a direct test on _build_spe_charge_line_field_values passing a mock or creating a ChargeAlias.
        # Wait, if we create a ChargeAlias with product_code pointing to something, resolved_product_code is not null.
        # But if we test it directly via _build_spe_charge_line_field_values:
        from django.utils import timezone
        from quotes.spot_views import _build_spe_charge_line_field_values
        spe = self._create_spe()

        # Let's create a ChargeAlias with a CanonicalChargeType but no product_code?
        # Wait, product_code is NOT NULL on ChargeAlias (on_delete=models.PROTECT).
        # But we can test that if canonical_charge_type is populated and resolved_product_code is null:
        # norm_fields = { "normalization_status": "MATCHED", "canonical_charge_type": ct, "resolved_product_code": None }
        # Let's test the helper _resolve_spe_charge_normalization_fields or verify normalization_review_reason via _build_spe_charge_line_field_values.
        # Let's create a test where we pass a charge to _build_spe_charge_line_field_values, but we mock resolve_charge_alias to return resolved_product_code=None.
        from unittest.mock import patch
        from quotes.services.charge_normalization import ChargeNormalizationResult, NormalizationStatus, NormalizationMethod

        mock_result = ChargeNormalizationResult(
            resolved_charge_alias=ChargeAlias(canonical_charge_type=self.ct_fuel),
            resolved_product_code=None,
            normalization_status=NormalizationStatus.MATCHED,
            normalization_method=NormalizationMethod.EXACT_ALIAS,
            raw_label='test label',
            normalized_label='test label'
        )

        with patch('quotes.spot_views.resolve_charge_alias', return_value=mock_result):
            fields = _build_spe_charge_line_field_values(
                spe_db=spe,
                charge={
                    'code': 'FSC_LINE',
                    'description': 'test label',
                    'amount': 100.00,
                    'currency': 'SGD',
                    'unit': 'flat',
                    'bucket': 'origin_charges',
                    'source_reference': 'REF-REV-2'
                },
                entered_by=self.user,
                entered_at=timezone.now(),
                shipment_context=spe.shipment_context_json
            )
            self.assertEqual(fields['normalization_review_reason'], 'product_code_missing')

    def test_ambiguous_alias_status_produces_ambiguous_product_mapping(self):
        """Verify ambiguous alias status maps to ambiguous_product_mapping review reason."""
        # Create two conflicting aliases to cause AMBIGUOUS status
        ChargeAlias.objects.create(
            alias_text='ambig raw label',
            normalized_alias_text='ambig raw label',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=self.pc,
            priority=5,
        )
        ChargeAlias.objects.create(
            alias_text='ambig raw label',
            normalized_alias_text='ambig raw label',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=self.pc_ambig,
            priority=5,
        )

        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'AMBIG_LINE',
                'description': 'ambig raw label',
                'amount': 50.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-REV-3'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.normalization_status, 'AMBIGUOUS')
        self.assertEqual(charge_line.normalization_review_reason, 'ambiguous_product_mapping')

    def test_conditional_canonical_type_produces_conditional_charge(self):
        """Verify conditional CanonicalChargeType maps to conditional_charge review reason."""
        # Create alias for a conditional charge type
        ChargeAlias.objects.create(
            alias_text='conditional storage label',
            normalized_alias_text='conditional storage label',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=self.pc,
            canonical_charge_type=self.ct_conditional,
            priority=5,
        )

        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'COND_LINE',
                'description': 'conditional storage label',
                'amount': 150.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-REV-4'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.canonical_charge_type, self.ct_conditional)
        self.assertEqual(charge_line.normalization_review_reason, 'conditional_charge')

    def test_matched_alias_with_product_code_produces_blank_review_reason(self):
        """Verify standard matched alias with product code has no review reason."""
        ChargeAlias.objects.create(
            alias_text='normal standard label',
            normalized_alias_text='normal standard label',
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.ANY,
            direction_scope=ChargeAlias.DirectionScope.ANY,
            product_code=self.pc,
            priority=5,
        )

        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line
        spe = self._create_spe()

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge={
                'code': 'NORMAL_LINE',
                'description': 'normal standard label',
                'amount': 50.00,
                'currency': 'SGD',
                'unit': 'flat',
                'bucket': 'origin_charges',
                'source_reference': 'REF-REV-5'
            },
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.normalization_status, 'MATCHED')
        self.assertIsNone(charge_line.normalization_review_reason)

    def test_manual_resolution_preserves_review_reason(self):
        """Verify that reconciliation preserves existing review reason if a line has manual resolution."""
        from django.utils import timezone
        from quotes.spot_views import _create_spe_charge_line, _build_spe_charge_line_field_values
        spe = self._create_spe()

        # Create line that starts as unmapped with canonical_type_missing
        charge_data = {
            'code': 'UNMAPPED_LINE',
            'description': 'random unknown label for manual resolution',
            'amount': 50.00,
            'currency': 'SGD',
            'unit': 'flat',
            'bucket': 'origin_charges',
            'source_reference': 'REF-REV-6'
        }

        charge_line = _create_spe_charge_line(
            spe_db=spe,
            charge=charge_data,
            entered_by=self.user,
            entered_at=timezone.now(),
            shipment_context=spe.shipment_context_json
        )
        self.assertEqual(charge_line.normalization_review_reason, 'canonical_type_missing')

        # Apply manual resolution
        charge_line.manual_resolved_product_code = self.pc
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

        # Check existing review reason is preserved instead of being recalculated/cleared
        self.assertEqual(fields['normalization_review_reason'], 'canonical_type_missing')


class SpotExpectedTemplateGroundworkTests(TestCase):
    """
    Test suite for Phase 10.3i — Expected Charge Template Framework Model Groundwork.
    """

    def setUp(self):
        # Fetch or create a test CanonicalChargeType
        self.ct_awb, _ = CanonicalChargeType.objects.get_or_create(
            code='AWB_DOCUMENTATION',
            defaults={
                'name': 'AWB Fee',
                'category': 'DOCUMENTATION'
            }
        )

    def test_expected_charge_template_creation(self):
        """Verify we can create ExpectedChargeTemplate with valid attributes."""
        from quotes.spot_models import ExpectedChargeTemplate
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export D2D Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="SG",
            origin_code="SIN",
            destination_country="PG",
            destination_code="POM"
        )
        self.assertIsNotNone(template.pk)
        self.assertEqual(template.name, "Airfreight Export D2D Template")

    def test_expected_template_line_creation(self):
        """Verify we can create ExpectedTemplateLine associated with template and canonical type."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export D2D Template",
            mode="EXPORT"
        )
        line = ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_awb,
            requirement_level="REQUIRED",
            expected_basis="flat"
        )
        self.assertIsNotNone(line.pk)
        self.assertEqual(line.template, template)
        self.assertEqual(line.canonical_charge_type, self.ct_awb)

    def test_duplicate_line_constraint(self):
        """Verify that adding two lines with the same canonical type triggers uniqueness IntegrityError."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine
        template = ExpectedChargeTemplate.objects.create(
            name="Duplicate Test Template",
            mode="EXPORT"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_awb,
            requirement_level="REQUIRED"
        )
        with self.assertRaises(IntegrityError):
            ExpectedTemplateLine.objects.create(
                template=template,
                canonical_charge_type=self.ct_awb,
                requirement_level="OPTIONAL"
            )

    def test_protect_behavior_on_canonical_charge_type_delete(self):
        """Verify deleting a CanonicalChargeType referenced by a Template Line raises ProtectedError."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine
        from django.db.models import ProtectedError
        template = ExpectedChargeTemplate.objects.create(
            name="Protect Test Template",
            mode="EXPORT"
        )
        ct_to_delete = CanonicalChargeType.objects.create(
            code="TEMP_TEST_PROTECT",
            name="Temp Test",
            category="TEST"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=ct_to_delete,
            requirement_level="REQUIRED"
        )
        with self.assertRaises(ProtectedError):
            ct_to_delete.delete()


class SpotExpectedTemplateValidationTests(TestCase):
    """
    Test suite for Phase 10.3j — SPOT Expected-vs-Actual Validation Engine.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='validation_analyst',
            email='validation@rateengine.com',
            password='testpassword',
            role='sales'
        )
        # Seed Canonical Charge Types
        cls.ct_awb = CanonicalChargeType.objects.create(
            code='AWB_DOCUMENTATION_VAL',
            name='AWB Fee',
            category='DOCUMENTATION'
        )
        cls.ct_fuel = CanonicalChargeType.objects.create(
            code='AIRLINE_FUEL_VAL',
            name='Airline Fuel Surcharge',
            category='FUEL'
        )
        cls.ct_delivery = CanonicalChargeType.objects.create(
            code='DEST_DELIVERY_VAL',
            name='Destination Delivery',
            category='DELIVERY'
        )
        cls.ct_storage = CanonicalChargeType.objects.create(
            code='CONDITIONAL_STORAGE_VAL',
            name='Conditional Storage',
            category='STORAGE'
        )

    def _create_spe(self, origin_code='POM', destination_code='SIN', origin_country='PG', destination_country='SG'):
        from django.utils import timezone
        return SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json={
                'origin_code': origin_code,
                'destination_code': destination_code,
                'origin_country': origin_country,
                'destination_country': destination_country,
                'service_scope': 'D2D',
                'transport_mode': 'AIR'
            },
            expires_at=timezone.now() + timezone.timedelta(hours=72)
        )

    def test_template_not_found(self):
        """Verify validation registers template_not_found if no active template matches."""
        from quotes.services.spot_template_validation import validate_envelope_charges
        spe = self._create_spe()
        
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        self.assertIsNone(result["template_id"])
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["code"], "template_not_found")
        self.assertEqual(result["findings"][0]["severity"], "Review")

    def test_missing_expected_charge(self):
        """Verify validation flags expected_charge_missing if REQUIRED line is absent."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine
        from quotes.services.spot_template_validation import validate_envelope_charges
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export SG->PG Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="PG",
            destination_country="SG"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_awb,
            requirement_level="REQUIRED"
        )
        
        spe = self._create_spe()
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        self.assertEqual(result["template_id"], template.id)
        findings = {f["code"] for f in result["findings"]}
        self.assertIn("expected_charge_missing", findings)

    def test_unexpected_charge_present(self):
        """Verify validation flags unexpected_charge_present if EXCLUDED line is present."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine, SPEChargeLineDB
        from quotes.services.spot_template_validation import validate_envelope_charges
        from django.utils import timezone
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export SG->PG Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="PG",
            destination_country="SG"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_delivery,
            requirement_level="EXCLUDED"
        )
        
        spe = self._create_spe()
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="EXCLUDED_LINE",
            description="some delivery charge",
            amount=500.0,
            currency="SGD",
            unit="flat",
            bucket="destination_charges",
            canonical_charge_type=self.ct_delivery,
            source_reference="REF-1",
            entered_by=self.user,
            entered_at=timezone.now()
        )
        
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        findings = {f["code"] for f in result["findings"]}
        self.assertIn("unexpected_charge_present", findings)

    def test_conditional_charge_present(self):
        """Verify validation flags conditional_charge_present if CONDITIONAL line is present."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine, SPEChargeLineDB
        from quotes.services.spot_template_validation import validate_envelope_charges
        from django.utils import timezone
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export SG->PG Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="PG",
            destination_country="SG"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_storage,
            requirement_level="CONDITIONAL"
        )
        
        spe = self._create_spe()
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="STORAGE_LINE",
            description="warehouse storage",
            amount=150.0,
            currency="SGD",
            unit="flat",
            bucket="destination_charges",
            canonical_charge_type=self.ct_storage,
            source_reference="REF-2",
            entered_by=self.user,
            entered_at=timezone.now()
        )
        
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        findings = {f["code"] for f in result["findings"]}
        self.assertIn("conditional_charge_present", findings)

    def test_duplicate_charge_family(self):
        """Verify validation flags duplicate_charge_family when actual canonical type is duplicated."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine, SPEChargeLineDB
        from quotes.services.spot_template_validation import validate_envelope_charges
        from django.utils import timezone
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export SG->PG Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="PG",
            destination_country="SG"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_fuel,
            requirement_level="REQUIRED"
        )
        
        spe = self._create_spe()
        # Add two fuel surcharge lines
        for ref in ["REF-A", "REF-B"]:
            SPEChargeLineDB.objects.create(
                envelope=spe,
                code="FUEL_LINE",
                description="airline fuel",
                amount=50.0,
                currency="SGD",
                unit="flat",
                bucket="airfreight",
                canonical_charge_type=self.ct_fuel,
                source_reference=ref,
                entered_by=self.user,
                entered_at=timezone.now()
            )
            
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        findings = {f["code"] for f in result["findings"]}
        self.assertIn("duplicate_charge_family", findings)

    def test_basis_mismatch(self):
        """Verify validation flags expected_basis_mismatch when actual basis differs from expected."""
        from quotes.spot_models import ExpectedChargeTemplate, ExpectedTemplateLine, SPEChargeLineDB
        from quotes.services.spot_template_validation import validate_envelope_charges
        from django.utils import timezone
        template = ExpectedChargeTemplate.objects.create(
            name="Airfreight Export SG->PG Template",
            mode="EXPORT",
            transport_mode="AIR",
            service_scope="D2D",
            origin_country="PG",
            destination_country="SG"
        )
        ExpectedTemplateLine.objects.create(
            template=template,
            canonical_charge_type=self.ct_fuel,
            requirement_level="REQUIRED",
            expected_basis="per_kg"
        )
        
        spe = self._create_spe()
        # Add actual line with flat calculation_basis snapshot
        SPEChargeLineDB.objects.create(
            envelope=spe,
            code="FUEL_LINE",
            description="airline fuel flat",
            amount=100.0,
            currency="SGD",
            unit="flat",
            bucket="airfreight",
            calculation_basis="flat",  # Mismatches expected_basis = 'per_kg'
            canonical_charge_type=self.ct_fuel,
            source_reference="REF-3",
            entered_by=self.user,
            entered_at=timezone.now()
        )
        
        result = validate_envelope_charges(spe)
        self.assertEqual(result["status"], "WARNINGS")
        findings = {f["code"] for f in result["findings"]}
        self.assertIn("expected_basis_mismatch", findings)





