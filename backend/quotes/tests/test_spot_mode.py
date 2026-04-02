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

from pricing_v4.models import ProductCode
from quotes.spot_schemas import (
    AIExtractedCharge,
    AISpotExtractionResult,
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SpotPricingEnvelope,
    SPEStatus,
)
from quotes.spot_services import (
    CommodityCoverageResult,
    ScopeValidator,
    SpotTriggerEvaluator,
    RateAvailabilityService,
    SpotEnvelopeService,
    SpotTriggerReason,
)
from quotes.completeness import (
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    COMPONENT_DESTINATION_LOCAL,
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

    def test_scope_valid_when_country_unknown_but_airports_identify_png_lane(self):
        """Fallback should resolve POM->SIN from airport codes when countries are OTHER."""
        is_valid, error = ScopeValidator.validate(
            origin_country="OTHER",
            destination_country="OTHER",
            origin_airport="POM",
            destination_airport="SIN",
        )

        assert is_valid is True
        assert error is None


# =============================================================================
# SPOT TRIGGER TESTS
# =============================================================================

class TestSpotTriggerEvaluation:
    """Deterministic SPOT trigger logic tests based on rate coverage."""
    
    def test_spot_trigger_out_of_scope(self):
        """Cross-trade (neither is PNG) triggers SPOT with OUT_OF_SCOPE."""
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="AU",
            destination_country="SG",
            direction="EXPORT",
            service_scope="P2P",
            component_availability={}
        )
        
        assert is_spot is True
        assert result.code == SpotTriggerReason.OUT_OF_SCOPE
    
    def test_spot_trigger_missing_airfreight(self):
        """Missing airfreight triggers SPOT."""
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="P2P",
            component_availability={COMPONENT_FREIGHT: False}
        )
        
        assert is_spot is True
        assert result.code == SpotTriggerReason.MISSING_SCOPE_RATES
        assert COMPONENT_FREIGHT in result.text
    
    def test_spot_trigger_complete_p2p(self):
        """Standard P2P with airfreight does NOT trigger SPOT."""
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="P2P",
            component_availability={COMPONENT_FREIGHT: True}
        )
        
        assert is_spot is False
        assert result is None
    
    def test_spot_trigger_missing_d2d_components(self):
        """D2D with missing destination charges triggers SPOT."""
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="D2D",
            component_availability={
                COMPONENT_ORIGIN_LOCAL: True,
                COMPONENT_FREIGHT: True,
                COMPONENT_DESTINATION_LOCAL: False,
            }
        )
        
        assert is_spot is True
        assert result.code == SpotTriggerReason.MISSING_SCOPE_RATES
        assert COMPONENT_DESTINATION_LOCAL in result.text

    def test_spot_trigger_commodity_no_longer_trigger(self):
        """Commodity type (like DG) is no longer a direct SPOT trigger in the evaluator."""
        # Note: DG might still be SPOT if rates are missing, but the evaluator 
        # itself no longer has commodity logic.
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="P2P",
            component_availability={COMPONENT_FREIGHT: True}
        )
        
        assert is_spot is False

    def test_spot_trigger_missing_commodity_rates(self):
        """Commodity-specific DB gaps trigger SPOT once base scope coverage is otherwise complete."""
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="D2A",
            component_availability={
                COMPONENT_ORIGIN_LOCAL: True,
                COMPONENT_FREIGHT: True,
            },
            commodity_code="DG",
            commodity_coverage=CommodityCoverageResult(
                missing_product_codes=["EXP-DG"]
            ),
        )

        assert is_spot is True
        assert result.code == SpotTriggerReason.MISSING_COMMODITY_RATES
        assert result.missing_product_codes == ["EXP-DG"]

    def test_spot_trigger_commodity_requires_spot_rule(self):
        ProductCode.objects.create(
            id=1977,
            code="EXP-AVI-SPOT",
            description="Export Live Animal Spot Charge",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="D2A",
            component_availability={
                COMPONENT_ORIGIN_LOCAL: True,
                COMPONENT_FREIGHT: True,
            },
            commodity_code="AVI",
            commodity_coverage=CommodityCoverageResult(
                spot_required_product_codes=["EXP-AVI-SPOT"],
            ),
        )

        assert is_spot is True
        assert result.code == SpotTriggerReason.COMMODITY_REQUIRES_SPOT
        assert result.spot_required_product_codes == ["EXP-AVI-SPOT"]
        assert "SPOT rate sourcing" in result.text
        assert "Export Live Animal Spot Charge (EXP-AVI-SPOT)" in result.text

    def test_spot_trigger_commodity_requires_manual_rule(self):
        ProductCode.objects.create(
            id=1976,
            code="EXP-AVI-MANUAL",
            description="Export Live Animal Manual Charge",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        ProductCode.objects.create(
            id=1975,
            code="EXP-AVI-DB",
            description="Export Live Animal Database Charge",
            domain="EXPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="PG",
            destination_country="AU",
            direction="EXPORT",
            service_scope="D2A",
            component_availability={
                COMPONENT_ORIGIN_LOCAL: True,
                COMPONENT_FREIGHT: True,
            },
            commodity_code="AVI",
            commodity_coverage=CommodityCoverageResult(
                manual_required_product_codes=["EXP-AVI-MANUAL"],
                spot_required_product_codes=["EXP-AVI-SPOT"],
                missing_product_codes=["EXP-AVI-DB"],
            ),
        )

        assert is_spot is True
        assert result.code == SpotTriggerReason.COMMODITY_REQUIRES_MANUAL
        assert result.manual_required_product_codes == ["EXP-AVI-MANUAL"]
        assert result.spot_required_product_codes == ["EXP-AVI-SPOT"]
        assert sorted(result.missing_product_codes) == sorted(
            ["EXP-AVI-MANUAL", "EXP-AVI-SPOT", "EXP-AVI-DB"]
        )
        assert "manual charge entry" in result.text
        assert "Export Live Animal Manual Charge (EXP-AVI-MANUAL)" in result.text
        assert "EXP-AVI-SPOT" in result.text
        assert "Export Live Animal Database Charge (EXP-AVI-DB)" in result.text


class TestRateAvailabilityService:
    """Rate availability detection against V4 rate tables."""

    def test_import_d2d_destination_side_import_local_rows_do_not_cover_origin_local(self):
        """
        IMPORT D2D must keep component side aligned:
        destination-side import local rows cannot satisfy ORIGIN_LOCAL.
        """
        from datetime import date, timedelta
        from pricing_v4.models import ProductCode, Agent, ImportCOGS, LocalCOGSRate

        valid_from = date.today() - timedelta(days=1)
        valid_until = date.today() + timedelta(days=30)

        agent = Agent.objects.create(
            code="SPOT-AU",
            name="Spot AU Agent",
            country_code="AU",
            agent_type="ORIGIN",
        )

        pc_freight = ProductCode.objects.create(
            id=2901,
            code="IMP-FRT-AIR-SPOTTEST",
            description="Import Air Freight (SPOT test)",
            domain="IMPORT",
            category="FREIGHT",
            is_gst_applicable=True,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        pc_origin = ProductCode.objects.create(
            id=2902,
            code="IMP-ORIGIN-HANDLING-SPOTTEST",
            description="Import Origin Handling (SPOT test)",
            domain="IMPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gl_revenue_code="4200",
            gl_cost_code="5200",
            default_unit="SHIPMENT",
        )
        pc_destination = ProductCode.objects.create(
            id=2903,
            code="IMP-CARTAGE-DEST-SPOTTEST",
            description="Import Destination Cartage (SPOT test)",
            domain="IMPORT",
            category="CARTAGE",
            is_gst_applicable=True,
            gl_revenue_code="4300",
            gl_cost_code="5300",
            default_unit="SHIPMENT",
        )

        ImportCOGS.objects.create(
            product_code=pc_freight,
            origin_airport="BNE",
            destination_airport="POM",
            agent=agent,
            currency="AUD",
            rate_per_kg=Decimal("4.50"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

        # Destination-side import local row with an ORIGIN code must not cover origin-local.
        LocalCOGSRate.objects.create(
            product_code=pc_origin,
            location="POM",
            direction="IMPORT",
            agent=agent,
            currency="AUD",
            rate_type="FIXED",
            amount=Decimal("75.00"),
            valid_from=valid_from,
            valid_until=valid_until,
        )
        LocalCOGSRate.objects.create(
            product_code=pc_destination,
            location="POM",
            direction="IMPORT",
            agent=agent,
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("120.00"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

        availability = RateAvailabilityService.get_availability(
            origin_airport="BNE",
            destination_airport="POM",
            direction="IMPORT",
            service_scope="D2D",
        )

        assert availability[COMPONENT_FREIGHT] is True
        assert availability[COMPONENT_ORIGIN_LOCAL] is False
        assert availability[COMPONENT_DESTINATION_LOCAL] is True


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

    def test_spe_allows_non_airfreight_when_scope_does_not_require_freight(self):
        """A2D SPE can contain destination-only charges without airfreight."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.DRAFT,
            shipment=SPEShipmentContext(
                origin_country="AU",
                destination_country="PG",
                origin_code="BNE",
                destination_code="POM",
                commodity="GCR",
                total_weight_kg=100.0,
                pieces=1,
                service_scope="a2d",
            ),
            charges=[
                SPEChargeLine(
                    code="DESTINATION_LOCAL",
                    description="Destination handling",
                    amount=75.0,
                    currency="USD",
                    unit="flat",
                    bucket="destination_charges",
                    is_primary_cost=False,
                    source_reference="Agent quote",
                    entered_by_user_id="user123",
                    entered_at=datetime.now()
                )
            ],
            conditions=SPEConditions(),
            spot_trigger_reason_code="MISSING_SCOPE_RATES",
            spot_trigger_reason_text="Missing destination local rates",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=72)
        )

        assert len(spe.charges) == 1
        assert spe.charges[0].bucket == "destination_charges"
    
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
    
    def test_acknowledgement_is_sufficient_for_pricing(self):
        """Acknowledged SPEs no longer require a separate manager approval gate."""
        spe = SpotPricingEnvelope(
            id=str(uuid4()),
            status=SPEStatus.READY,
            shipment=SPEShipmentContext(
                origin_country="PG",
                destination_country="AU",
                origin_code="POM",
                destination_code="BNE",
                commodity="DG",
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
            spot_trigger_reason_code="DG_COMMODITY",
            spot_trigger_reason_text="Dangerous Goods",
            created_by_user_id="user123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=72)
        )
        
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        assert is_valid is True
        assert error is None
    
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


