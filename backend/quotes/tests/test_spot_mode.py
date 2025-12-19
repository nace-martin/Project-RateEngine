# backend/quotes/tests/test_spot_mode.py
"""
SPOT Mode Unit Tests

TDD approach: Tests written first, then implementation.
These tests cover ALL guardrails for SPOT Mode.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import hashlib
import json

from django.contrib.auth import get_user_model
from django.utils import timezone

from quotes.spot_schemas import (
    AIExtractedCharge,
    AISpotExtractionResult,
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SPEManagerApproval,
    SpotPricingEnvelope,
    SPEStatus,
)
from quotes.spot_services import (
    ScopeValidator,
    SpotTriggerEvaluator,
    SpotEnvelopeService,
    SpotTriggerReason,
)


pytestmark = pytest.mark.django_db


# =============================================================================
# SCOPE VALIDATION TESTS (Tweak #1)
# =============================================================================

class TestScopeValidation:
    """PNG-only scope enforcement. Request-boundary validation."""
    
    def test_scope_rejection_mel_to_lax(self):
        """MEL→LAX must be rejected outright. No SPOT. No workaround."""
        is_valid, error = ScopeValidator.validate(
            origin_country="AU",
            destination_country="US"
        )
        
        assert is_valid is False
        assert "out of scope" in error.lower()
        assert "Papua New Guinea" in error or "PNG" in error
    
    def test_scope_rejection_syd_to_sin(self):
        """SYD→SIN (neither is PNG) must be rejected."""
        is_valid, error = ScopeValidator.validate(
            origin_country="AU",
            destination_country="SG"
        )
        
        assert is_valid is False
        assert "out of scope" in error.lower()
    
    def test_scope_valid_export_from_png(self):
        """POM→SYD (export from PNG) is valid."""
        is_valid, error = ScopeValidator.validate(
            origin_country="PG",
            destination_country="AU"
        )
        
        assert is_valid is True
        assert error is None
    
    def test_scope_valid_import_to_png(self):
        """BNE→POM (import to PNG) is valid."""
        is_valid, error = ScopeValidator.validate(
            origin_country="AU",
            destination_country="PG"
        )
        
        assert is_valid is True
        assert error is None
    
    def test_scope_valid_domestic_png(self):
        """POM→LAE (domestic PNG) is valid."""
        is_valid, error = ScopeValidator.validate(
            origin_country="PG",
            destination_country="PG"
        )
        
        assert is_valid is True
        assert error is None


# =============================================================================
# SPOT TRIGGER TESTS
# =============================================================================

class TestSpotTriggerEvaluation:
    """Centralised SPOT trigger logic tests."""
    
    def test_spot_trigger_dg_commodity(self):
        """Dangerous Goods triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="DG"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.DG_COMMODITY
        assert "Dangerous Goods" in reason.text
    
    def test_spot_trigger_avi_commodity(self):
        """Live Animals triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="AVI"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.AVI_COMMODITY
        assert "Live Animals" in reason.text
    
    def test_spot_trigger_per_commodity(self):
        """Perishables triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="PER"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.PER_COMMODITY
        assert "Perishables" in reason.text
    
    def test_spot_trigger_non_px_export_route(self):
        """Export to destination not served by Air Niugini triggers SPOT."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="US",  # LAX - not PX direct
            commodity="GCR"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.NON_PX_ROUTE
        assert "Air Niugini" in reason.text
    
    def test_spot_trigger_normal_pricing(self):
        """Standard POM→BNE GCR does NOT trigger SPOT."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="GCR",
            destination_airport="BNE"  # PX direct route
        )
        
        assert is_spot is False
        assert reason is None
    
    def test_spot_trigger_hvc_commodity(self):
        """High Value Cargo triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="HVC"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.HVC_COMMODITY
        assert "High Value" in reason.text
    
    def test_spot_trigger_oog_commodity(self):
        """Oversized/Heavy cargo triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="OOG"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.OOG_COMMODITY
        assert "Oversized" in reason.text
    
    def test_spot_trigger_vul_commodity(self):
        """Vulnerable Cargo triggers SPOT mode."""
        is_spot, reason = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            commodity="VUL"
        )
        
        assert is_spot is True
        assert reason.code == SpotTriggerReason.VUL_COMMODITY
        assert "Vulnerable" in reason.text


# =============================================================================
# SPE SCHEMA VALIDATION TESTS (Tweaks #2, #4)
# =============================================================================

class TestSPESchemaValidation:
    """Pydantic schema guardrails for Spot Pricing Envelope."""
    
    def test_spe_png_guardrail_rejects_non_png(self):
        """SPE creation fails if not PNG-related."""
        with pytest.raises(ValueError) as exc_info:
            SpotPricingEnvelope(
                id=str(uuid4()),
                status=SPEStatus.DRAFT,
                shipment=SPEShipmentContext(
                    origin_country="AU",
                    destination_country="US",  # Neither is PNG
                    origin_code="MEL",
                    destination_code="LAX",
                    commodity="GCR",
                    total_weight_kg=100.0,
                    pieces=1
                ),
                charges=[
                    SPEChargeLine(
                        code="AIRFREIGHT_SPOT",
                        description="Airfreight",
                        amount=500.0,
                        currency="USD",
                        unit="per_kg",
                        bucket="airfreight",
                        is_primary_cost=True,
                        source_reference="Email from agent",
                        entered_by_user_id="user123",
                        entered_at=datetime.now()
                    )
                ],
                conditions=SPEConditions(),
                spot_trigger_reason_code="TEST",
                spot_trigger_reason_text="Test",
                created_by_user_id="user123",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=72)
            )
        
        assert "out of scope" in str(exc_info.value).lower() or "PNG" in str(exc_info.value)
    
    def test_spe_single_airfreight_rejects_zero(self):
        """SPE requires exactly one primary airfreight charge."""
        with pytest.raises(ValueError) as exc_info:
            SpotPricingEnvelope(
                id=str(uuid4()),
                status=SPEStatus.DRAFT,
                shipment=SPEShipmentContext(
                    origin_country="PG",
                    destination_country="AU",
                    origin_code="POM",
                    destination_code="BNE",
                    commodity="GCR",
                    total_weight_kg=100.0,
                    pieces=1
                ),
                charges=[
                    # No airfreight charge - only origin handling
                    SPEChargeLine(
                        code="HANDLING",
                        description="Handling",
                        amount=50.0,
                        currency="USD",
                        unit="flat",
                        bucket="origin_charges",
                        is_primary_cost=False,
                        source_reference="Email",
                        entered_by_user_id="user123",
                        entered_at=datetime.now()
                    )
                ],
                conditions=SPEConditions(),
                spot_trigger_reason_code="TEST",
                spot_trigger_reason_text="Test",
                created_by_user_id="user123",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=72)
            )
        
        assert "airfreight" in str(exc_info.value).lower()
    
    def test_spe_single_airfreight_rejects_multiple(self):
        """SPE rejects two airfreight/primary charges."""
        with pytest.raises(ValueError) as exc_info:
            SpotPricingEnvelope(
                id=str(uuid4()),
                status=SPEStatus.DRAFT,
                shipment=SPEShipmentContext(
                    origin_country="PG",
                    destination_country="AU",
                    origin_code="POM",
                    destination_code="BNE",
                    commodity="GCR",
                    total_weight_kg=100.0,
                    pieces=1
                ),
                charges=[
                    SPEChargeLine(
                        code="AIRFREIGHT_SPOT",
                        description="Airfreight Leg 1",
                        amount=500.0,
                        currency="USD",
                        unit="per_kg",
                        bucket="airfreight",
                        is_primary_cost=True,
                        source_reference="Email 1",
                        entered_by_user_id="user123",
                        entered_at=datetime.now()
                    ),
                    SPEChargeLine(
                        code="AIRFREIGHT_SPOT",
                        description="Airfreight Leg 2",
                        amount=300.0,
                        currency="USD",
                        unit="per_kg",
                        bucket="airfreight",
                        is_primary_cost=True,  # Two primary costs!
                        source_reference="Email 2",
                        entered_by_user_id="user123",
                        entered_at=datetime.now()
                    )
                ],
                conditions=SPEConditions(),
                spot_trigger_reason_code="TEST",
                spot_trigger_reason_text="Test",
                created_by_user_id="user123",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=72)
            )
        
        assert "one" in str(exc_info.value).lower() or "single" in str(exc_info.value).lower()
    
    def test_spe_shipment_context_frozen(self):
        """SPEShipmentContext cannot be mutated after creation."""
        ctx = SPEShipmentContext(
            origin_country="PG",
            destination_country="AU",
            origin_code="POM",
            destination_code="BNE",
            commodity="GCR",
            total_weight_kg=100.0,
            pieces=1
        )
        
        with pytest.raises(Exception):  # Pydantic frozen model raises error
            ctx.origin_code = "LAE"  # Attempt mutation
    
    def test_spe_context_hash_generated(self):
        """SPE generates hash for shipment context integrity verification."""
        ctx = SPEShipmentContext(
            origin_country="PG",
            destination_country="AU",
            origin_code="POM",
            destination_code="BNE",
            commodity="GCR",
            total_weight_kg=100.0,
            pieces=1
        )
        
        assert ctx.context_hash is not None
        assert len(ctx.context_hash) == 64  # SHA256 hex digest


# =============================================================================
# SPE LIFECYCLE TESTS (Tweak #3)
# =============================================================================

class TestSPELifecycle:
    """SPE lifecycle: expiry, acknowledgement, approval."""
    
    def test_expired_spe_blocks_pricing(self):
        """Expired SPE cannot be used for pricing."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.READY,
            shipment=SPEShipmentContext(
                origin_country="PG",
                destination_country="AU",
                origin_code="POM",
                destination_code="BNE",
                commodity="GCR",
                total_weight_kg=100.0,
                pieces=1
            ),
            charges=[
                SPEChargeLine(
                    code="AIRFREIGHT_SPOT",
                    description="Airfreight",
                    amount=500.0,
                    currency="USD",
                    unit="per_kg",
                    bucket="airfreight",
                    is_primary_cost=True,
                    source_reference="Email",
                    entered_by_user_id="user123",
                    entered_at=datetime.now()
                )
            ],
            conditions=SPEConditions(),
            acknowledgement=SPEAcknowledgement(
                acknowledged_by_user_id="user123",
                acknowledged_at=datetime.now(),
                statement="I acknowledge this is a conditional SPOT quote and not guaranteed"
            ),
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() - timedelta(hours=1)  # EXPIRED
        )
        
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        assert is_valid is False
        assert "expired" in error.lower()
    
    def test_missing_acknowledgement_blocks_pricing(self):
        """SPE without Sales acknowledgement cannot be used for pricing."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.READY,
            shipment=SPEShipmentContext(
                origin_country="PG",
                destination_country="AU",
                origin_code="POM",
                destination_code="BNE",
                commodity="GCR",
                total_weight_kg=100.0,
                pieces=1
            ),
            charges=[
                SPEChargeLine(
                    code="AIRFREIGHT_SPOT",
                    description="Airfreight",
                    amount=500.0,
                    currency="USD",
                    unit="per_kg",
                    bucket="airfreight",
                    is_primary_cost=True,
                    source_reference="Email",
                    entered_by_user_id="user123",
                    entered_at=datetime.now()
                )
            ],
            conditions=SPEConditions(),
            acknowledgement=None,  # MISSING
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=72)
        )
        
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        assert is_valid is False
        assert "acknowledgement" in error.lower()
    
    def test_missing_manager_approval_blocks_when_required(self):
        """SPE requiring manager approval blocks without it."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.READY,
            shipment=SPEShipmentContext(
                origin_country="PG",
                destination_country="AU",
                origin_code="POM",
                destination_code="BNE",
                commodity="DG",  # DG requires approval
                total_weight_kg=100.0,
                pieces=1
            ),
            charges=[
                SPEChargeLine(
                    code="AIRFREIGHT_SPOT",
                    description="Airfreight",
                    amount=500.0,
                    currency="USD",
                    unit="per_kg",
                    bucket="airfreight",
                    is_primary_cost=True,
                    source_reference="Email",
                    entered_by_user_id="user123",
                    entered_at=datetime.now()
                )
            ],
            conditions=SPEConditions(),
            acknowledgement=SPEAcknowledgement(
                acknowledged_by_user_id="user123",
                acknowledged_at=datetime.now(),
                statement="I acknowledge this is a conditional SPOT quote and not guaranteed"
            ),
            manager_approval=None,  # MISSING but required for DG
            spot_trigger_reason_code="DG_COMMODITY",
            spot_trigger_reason_text="Dangerous Goods",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=72)
        )
        
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        assert is_valid is False
        assert "manager approval" in error.lower()
    
    def test_draft_status_blocks_pricing(self):
        """SPE in DRAFT status cannot be used for pricing."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.DRAFT,  # Not READY
            shipment=SPEShipmentContext(
                origin_country="PG",
                destination_country="AU",
                origin_code="POM",
                destination_code="BNE",
                commodity="GCR",
                total_weight_kg=100.0,
                pieces=1
            ),
            charges=[
                SPEChargeLine(
                    code="AIRFREIGHT_SPOT",
                    description="Airfreight",
                    amount=500.0,
                    currency="USD",
                    unit="per_kg",
                    bucket="airfreight",
                    is_primary_cost=True,
                    source_reference="Email",
                    entered_by_user_id="user123",
                    entered_at=datetime.now()
                )
            ],
            conditions=SPEConditions(),
            acknowledgement=SPEAcknowledgement(
                acknowledged_by_user_id="user123",
                acknowledged_at=datetime.now(),
                statement="I acknowledge this is a conditional SPOT quote and not guaranteed"
            ),
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=72)
        )
        
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        assert is_valid is False
        assert "status" in error.lower() or "ready" in error.lower()


# =============================================================================
# AI EXTRACTION SCHEMA TESTS
# =============================================================================

class TestAIExtractionSchemas:
    """AI extraction output validation (untrusted input)."""
    
    def test_ai_extracted_charge_valid(self):
        """Valid AI extraction creates charge object."""
        charge = AIExtractedCharge(
            raw_text="Airfreight: USD 5.50/kg",
            amount=5.50,
            currency="USD",
            unit="per_kg",
            suggested_code="AIRFREIGHT",
            suggested_bucket="airfreight",
            conditional=False,
            confidence=0.85
        )
        
        assert charge.amount == 5.50
        assert charge.confidence == 0.85
    
    def test_ai_extracted_charge_with_missing_amount(self):
        """AI can extract text even with missing numeric value."""
        charge = AIExtractedCharge(
            raw_text="Subject to space confirmation",
            amount=None,  # Not extractable
            currency=None,
            unit="unknown",
            suggested_code=None,
            suggested_bucket="unknown",
            conditional=True,
            confidence=0.3
        )
        
        assert charge.amount is None
        assert charge.conditional is True
    
    def test_ai_extraction_result_with_warnings(self):
        """AI extraction result includes warnings."""
        result = AISpotExtractionResult(
            source_type="email",
            extracted_at=datetime.now(),
            charges=[
                AIExtractedCharge(
                    raw_text="Rate TBC",
                    amount=None,
                    currency=None,
                    unit="unknown",
                    suggested_code=None,
                    suggested_bucket="unknown",
                    conditional=True,
                    confidence=0.2
                )
            ],
            warnings=["Rate value not specified", "Currency missing"],
            notes="Email contains conditional language"
        )
        
        assert len(result.warnings) == 2
        assert result.charges[0].conditional is True


# =============================================================================
# MANAGER APPROVAL POLICY TESTS (Tweak #6)
# =============================================================================

class TestManagerApprovalPolicy:
    """Manager approval thresholds as policy, not if-statements."""
    
    def test_dg_requires_approval(self):
        """DG shipments require manager approval per policy."""
        from quotes.spot_services import SpotApprovalPolicy
        
        requires = SpotApprovalPolicy.requires_manager_approval(
            commodity="DG",
            margin_percent=Decimal("20.0"),
            is_multi_leg=False
        )
        
        assert requires is True
    
    def test_multi_leg_requires_approval(self):
        """Multi-leg routing requires manager approval per policy."""
        from quotes.spot_services import SpotApprovalPolicy
        
        requires = SpotApprovalPolicy.requires_manager_approval(
            commodity="GCR",
            margin_percent=Decimal("20.0"),
            is_multi_leg=True
        )
        
        assert requires is True
    
    def test_low_margin_requires_approval(self):
        """Low margin (below threshold) requires manager approval."""
        from quotes.spot_services import SpotApprovalPolicy
        
        requires = SpotApprovalPolicy.requires_manager_approval(
            commodity="GCR",
            margin_percent=Decimal("10.0"),  # Below threshold
            is_multi_leg=False
        )
        
        assert requires is True
    
    def test_standard_gcr_no_approval_needed(self):
        """Standard GCR with good margin does not require approval."""
        from quotes.spot_services import SpotApprovalPolicy
        
        requires = SpotApprovalPolicy.requires_manager_approval(
            commodity="GCR",
            margin_percent=Decimal("25.0"),  # Above threshold
            is_multi_leg=False
        )
        
        assert requires is False
