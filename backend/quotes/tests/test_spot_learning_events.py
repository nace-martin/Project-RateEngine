# backend/quotes/tests/test_spot_learning_events.py
"""
Tests for Phase 10.3a: SPOT Resolution Learning Event Capture

Verifies that SpotResolutionLearningEvent rows are created when users
resolve manual and conditional SPOT charge exceptions through the API.
"""

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Location
from core.tests.helpers import create_location
from pricing_v4.models import ProductCode, ChargeAlias
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPESourceBatchDB,
    SPEChargeLineDB,
)
from quotes.spot_learning_models import (
    SpotResolutionLearningEvent,
)

User = get_user_model()


class SpotLearningEventModelTest(APITestCase):
    """Test SpotResolutionLearningEvent model."""

    def test_learning_event_model_exists(self):
        """Verify the learning event model is available and has correct table name."""
        self.assertEqual(
            SpotResolutionLearningEvent._meta.db_table,
            'spot_resolution_learning_events',
        )

    def test_learning_event_resolution_types(self):
        """Verify all expected resolution types are defined."""
        expected = {
            'MANUAL_PRODUCT_CODE',
            'CONFIRM_PATTERN_MATCH',
            'OVERRIDE_SUGGESTION',
            'CONDITIONAL_KEEP',
            'CONDITIONAL_REMOVE',
            'AUTO_RESOLVED',
        }
        actual = {choice[0] for choice in SpotResolutionLearningEvent.ResolutionType.choices}
        self.assertEqual(actual, expected)



class SpotLearningEventCaptureBaseTest(APITestCase):
    """Base class with shared setup for learning event capture tests."""

    @classmethod
    def setUpTestData(cls):
        cls.sales_user = User.objects.create_user(
            username='le_sales', password='testpass123', role=User.ROLE_SALES,
        )
        cls.manager_user = User.objects.create_user(
            username='le_manager', password='testpass123', role=User.ROLE_MANAGER,
        )
        cls.admin_user = User.objects.create_user(
            username='le_admin', password='testpass123', role=User.ROLE_ADMIN,
        )

        # Product codes for resolution targets — use get_or_create to avoid
        # collision with seeded data migrations.
        cls.pc_handling, _ = ProductCode.objects.get_or_create(
            id=2970,
            defaults=dict(
                code='IMP_HANDLING_LE', description='Import Handling (LE Test)',
                domain=ProductCode.DOMAIN_IMPORT, category=ProductCode.CATEGORY_HANDLING,
                is_gst_applicable=True, gl_revenue_code='4100', gl_cost_code='5100',
            ),
        )
        cls.pc_customs, _ = ProductCode.objects.get_or_create(
            id=2971,
            defaults=dict(
                code='IMP_CUSTOMS_LE', description='Import Customs (LE Test)',
                domain=ProductCode.DOMAIN_IMPORT, category=ProductCode.CATEGORY_CLEARANCE,
                is_gst_applicable=True, gl_revenue_code='4200', gl_cost_code='5200',
            ),
        )

    def _create_spe_with_charge(
        self,
        user,
        *,
        normalization_status='UNMAPPED',
        normalization_method='NONE',
        conditional=False,
        source_label='Handling Fee',
        resolved_product_code=None,
    ):
        """Helper to create an SPE with a single charge line for testing."""
        import hashlib
        import json

        ctx = {
            'origin_code': 'SYD',
            'destination_code': 'POM',
            'mode': 'AIR',
            'shipment_type': 'IMPORT',
            'service_scope': 'D2D',
        }
        ctx_json = json.dumps(ctx, sort_keys=True)
        ctx_hash = hashlib.sha256(ctx_json.encode()).hexdigest()

        spe = SpotPricingEnvelopeDB.objects.create(
            status='draft',
            shipment_context_json=ctx,
            shipment_context_hash=ctx_hash,
            spot_trigger_reason_code='NO_RATE_COVERAGE',
            spot_trigger_reason_text='No rate coverage for test',
            created_by=user,
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

        batch = SPESourceBatchDB.objects.create(
            envelope=spe,
            source_kind='AGENT',
            source_type='TEXT',
            target_bucket='destination_charges',
            label='Test Agent Co',
            source_reference='test-email-ref',
            created_by=user,
        )

        charge_line = SPEChargeLineDB.objects.create(
            envelope=spe,
            source_batch=batch,
            code='HANDLING_SPOT',
            description=source_label,
            amount=Decimal('150.00'),
            currency='PGK',
            unit='per_shipment',
            bucket='destination_charges',
            source_label=source_label,
            normalized_label=source_label.lower().strip(),
            normalization_status=normalization_status,
            normalization_method=normalization_method,
            resolved_product_code=resolved_product_code,
            conditional=conditional,
            source_reference='test-ref',
            entered_by=user,
            entered_at=timezone.now(),
        )

        return spe, batch, charge_line


class ManualResolutionLearningEventTest(SpotLearningEventCaptureBaseTest):
    """Test that manual SPOT charge resolution captures learning events."""

    def test_manual_resolution_creates_learning_event(self):
        """UNMAPPED charge line → user selects ProductCode → learning event recorded."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='UNMAPPED',
            normalization_method='NONE',
            source_label='Terminal Handling Charge',
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_handling.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify learning event was created
        events = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        )
        self.assertEqual(events.count(), 1)

        event = events.first()
        self.assertEqual(event.resolution_type, 'MANUAL_PRODUCT_CODE')
        self.assertEqual(event.normalized_label, 'terminal handling charge')
        self.assertEqual(event.bucket, 'destination_charges')
        self.assertEqual(event.normalization_status_before, 'UNMAPPED')
        self.assertEqual(event.normalization_method_before, 'NONE')
        self.assertIsNone(event.system_suggested_product_code)
        self.assertEqual(event.resolved_product_code_id, self.pc_handling.id)
        self.assertFalse(event.user_agreed_with_suggestion)
        self.assertEqual(event.resolved_by, self.sales_user)
        self.assertIsNone(event.confidence_at_resolution)

    def test_manual_resolution_captures_shipment_context(self):
        """Verify denormalized shipment context is captured in the learning event."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.manager_user,
            source_label='Customs Clearance',
        )

        self.client.force_authenticate(user=self.manager_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_customs.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.origin_code, 'SYD')
        self.assertEqual(event.destination_code, 'POM')
        self.assertEqual(event.mode, 'AIR')
        self.assertEqual(event.shipment_type, 'IMPORT')
        self.assertEqual(event.service_scope, 'D2D')

    def test_manual_resolution_captures_source_context(self):
        """Verify source batch context (supplier info) is captured."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            source_label='Agency Fee',
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_handling.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.source_kind, 'AGENT')
        self.assertEqual(event.source_label_supplier, 'Test Agent Co')

    def test_pattern_match_confirmation_creates_confirm_event(self):
        """PATTERN_ALIAS match → user confirms same ProductCode → CONFIRM_PATTERN_MATCH."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='MATCHED',
            normalization_method='PATTERN_ALIAS',
            source_label='Terminal Handling',
            resolved_product_code=self.pc_handling,
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_handling.id,  # Same as system suggested
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.resolution_type, 'CONFIRM_PATTERN_MATCH')
        self.assertTrue(event.user_agreed_with_suggestion)
        self.assertEqual(event.system_suggested_product_code_id, self.pc_handling.id)
        self.assertEqual(event.resolved_product_code_id, self.pc_handling.id)

    def test_pattern_match_override_creates_manual_event(self):
        """PATTERN_ALIAS match → user picks DIFFERENT ProductCode → MANUAL_PRODUCT_CODE."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='MATCHED',
            normalization_method='PATTERN_ALIAS',
            source_label='Terminal Handling',
            resolved_product_code=self.pc_handling,
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_customs.id,  # Different from suggestion
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.resolution_type, 'MANUAL_PRODUCT_CODE')
        self.assertFalse(event.user_agreed_with_suggestion)
        self.assertEqual(event.system_suggested_product_code_id, self.pc_handling.id)
        self.assertEqual(event.resolved_product_code_id, self.pc_customs.id)

    def test_ambiguous_resolution_creates_learning_event(self):
        """AMBIGUOUS charge → user disambiguates → learning event with AMBIGUOUS status."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.admin_user,
            normalization_status='AMBIGUOUS',
            normalization_method='EXACT_ALIAS',
            source_label='Clearance Fee',
        )

        self.client.force_authenticate(user=self.admin_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_customs.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.normalization_status_before, 'AMBIGUOUS')
        self.assertEqual(event.resolved_by, self.admin_user)

    def test_multiple_resolutions_create_multiple_events(self):
        """Resolving the same charge line twice creates two learning events (append-only)."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='UNMAPPED',
            source_label='Doc Fee',
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'

        # First resolution
        self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_handling.id,
        }, format='json')

        # Second resolution (user changed their mind)
        self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_customs.id,
        }, format='json')

        events = SpotResolutionLearningEvent.objects.filter(
            charge_line=charge_line,
        )
        self.assertEqual(events.count(), 2)


class ConditionalResolutionLearningEventTest(SpotLearningEventCaptureBaseTest):
    """Test that conditional SPOT charge resolution captures learning events."""

    def test_conditional_keep_creates_learning_event(self):
        """Conditional charge → KEEP → CONDITIONAL_KEEP learning event."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='MATCHED',
            normalization_method='EXACT_ALIAS',
            conditional=True,
            source_label='Quarantine Inspection',
            resolved_product_code=self.pc_handling,
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/conditional-resolution/'
        response = self.client.patch(url, {
            'action': 'KEEP',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        events = SpotResolutionLearningEvent.objects.filter(
            envelope=spe,
            resolution_type='CONDITIONAL_KEEP',
        )
        self.assertEqual(events.count(), 1)

        event = events.first()
        self.assertEqual(event.normalized_label, 'quarantine inspection')
        self.assertEqual(event.bucket, 'destination_charges')
        self.assertEqual(event.resolved_product_code_id, self.pc_handling.id)
        self.assertEqual(event.resolved_by, self.sales_user)

    def test_conditional_remove_creates_learning_event(self):
        """Conditional charge → REMOVE → CONDITIONAL_REMOVE learning event."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='MATCHED',
            normalization_method='EXACT_ALIAS',
            conditional=True,
            source_label='Optional Storage Fee',
            resolved_product_code=self.pc_handling,
        )
        charge_line_id = charge_line.id

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line_id}/conditional-resolution/'
        response = self.client.patch(url, {
            'action': 'REMOVE',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Charge line was deleted, but learning event was recorded BEFORE delete
        events = SpotResolutionLearningEvent.objects.filter(
            envelope=spe,
            resolution_type='CONDITIONAL_REMOVE',
        )
        self.assertEqual(events.count(), 1)

        event = events.first()
        self.assertEqual(event.normalized_label, 'optional storage fee')
        self.assertIsNone(event.resolved_product_code)  # REMOVE has no product code
        self.assertEqual(event.resolved_by, self.sales_user)

    def test_conditional_keep_captures_shipment_context(self):
        """Verify conditional resolution captures full shipment context."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.manager_user,
            conditional=True,
            source_label='Fumigation if required',
            resolved_product_code=self.pc_customs,
        )

        self.client.force_authenticate(user=self.manager_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/conditional-resolution/'
        response = self.client.patch(url, {
            'action': 'KEEP',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = SpotResolutionLearningEvent.objects.filter(envelope=spe).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.origin_code, 'SYD')
        self.assertEqual(event.destination_code, 'POM')
        self.assertEqual(event.mode, 'AIR')
        self.assertEqual(event.shipment_type, 'IMPORT')
        self.assertEqual(event.source_kind, 'AGENT')
        self.assertEqual(event.source_label_supplier, 'Test Agent Co')

    def test_invalid_action_returns_400_no_event(self):
        """Invalid conditional action returns 400 and no learning event is created."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            conditional=True,
            source_label='Some Charge',
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/conditional-resolution/'
        response = self.client.patch(url, {
            'action': 'INVALID',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        events = SpotResolutionLearningEvent.objects.filter(envelope=spe)
        self.assertEqual(events.count(), 0)


class LearningEventDoesNotAffectResolutionTest(SpotLearningEventCaptureBaseTest):
    """Verify that learning event recording does not change resolution behavior."""

    def test_manual_resolution_still_updates_charge_line(self):
        """Charge line fields are still correctly updated after resolution."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            normalization_status='UNMAPPED',
            source_label='Delivery Fee',
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/manual-resolution/'
        response = self.client.patch(url, {
            'manual_resolved_product_code_id': self.pc_handling.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        charge_line.refresh_from_db()
        self.assertEqual(
            charge_line.manual_resolution_status,
            SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
        )
        self.assertEqual(charge_line.manual_resolved_product_code_id, self.pc_handling.id)
        self.assertEqual(charge_line.manual_resolution_by, self.sales_user)

    def test_conditional_keep_still_acknowledges_charge(self):
        """Conditional KEEP still sets acknowledged fields on the charge line."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            conditional=True,
            source_label='Inspection',
            resolved_product_code=self.pc_handling,
        )

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line.id}/conditional-resolution/'
        self.client.patch(url, {'action': 'KEEP'}, format='json')

        charge_line.refresh_from_db()
        self.assertTrue(charge_line.conditional_acknowledged)
        self.assertEqual(charge_line.conditional_acknowledged_by, self.sales_user)

    def test_conditional_remove_still_deletes_charge(self):
        """Conditional REMOVE still deletes the charge line."""
        spe, batch, charge_line = self._create_spe_with_charge(
            self.sales_user,
            conditional=True,
            source_label='Optional Fee',
            resolved_product_code=self.pc_handling,
        )
        charge_line_id = charge_line.id

        self.client.force_authenticate(user=self.sales_user)
        url = f'/api/v3/spot/envelopes/{spe.id}/charges/{charge_line_id}/conditional-resolution/'
        self.client.patch(url, {'action': 'REMOVE'}, format='json')

        self.assertFalse(
            SPEChargeLineDB.objects.filter(id=charge_line_id).exists()
        )
