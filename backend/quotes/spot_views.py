# backend/quotes/spot_views.py
"""
SPOT Mode API Endpoints

Endpoints:
- POST /api/v3/spot/validate-scope/     - Validate shipment is PNG scope
- POST /api/v3/spot/evaluate-trigger/   - Check if SPOT mode required
- POST /api/v3/spot/envelopes/          - Create SPE
- GET  /api/v3/spot/envelopes/<id>/     - Get SPE
- POST /api/v3/spot/envelopes/<id>/acknowledge/  - Sales acknowledgement
- POST /api/v3/spot/envelopes/<id>/approve/      - Manager approval
- POST /api/v3/spot/envelopes/<id>/compute/      - Compute SPOT quote
"""

import logging
import uuid
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID

from django.utils import timezone

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from django.shortcuts import get_object_or_404

from quotes.spot_services import (
    ScopeValidator,
    SpotTriggerEvaluator,
    SpotApprovalPolicy,
    SpotEnvelopeService,
    SpotTriggerReason,
    TriggerResult,
    ReplyAnalysisService,
)
from quotes.spot_schemas import (
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SPEManagerApproval,
    SpotPricingEnvelope,
    SPEStatus,
)
from quotes.models import (
    SpotPricingEnvelopeDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
    SPEManagerApprovalDB,
)


logger = logging.getLogger(__name__)


def _user_can_access_spe(user, spe_db: SpotPricingEnvelopeDB) -> bool:
    if not user or not user.is_authenticated:
        return False
    user_role = getattr(user, 'role', '')
    if user_role in ['manager', 'admin']:
        return True
    return spe_db.created_by_id == user.id


def _get_missing_mandatory_fields(spe_db: SpotPricingEnvelopeDB) -> list:
    """
    Compute missing mandatory fields for SPE.
    Required: rate (at least one charge with amount), currency
    """
    missing = []
    charges = list(spe_db.charge_lines.all())
    
    # Check if we have at least one rate charge
    has_rate = any(
        cl.amount is not None and float(cl.amount) > 0 
        for cl in charges
    )
    if not has_rate:
        missing.append('rate')
    
    # Check if all charges have currency
    has_currency = all(cl.currency for cl in charges) if charges else False
    if not has_currency:
        missing.append('currency')
    
    return missing


def _get_spe_or_404(user, envelope_id, queryset=None):
    spe_db = get_object_or_404(queryset or SpotPricingEnvelopeDB, id=envelope_id)
    if not _user_can_access_spe(user, spe_db):
        raise PermissionDenied("You do not have access to this SPOT envelope.")
    return spe_db


def _build_spe_from_db(
    spe_db: SpotPricingEnvelopeDB,
    status_override: Optional[str] = None,
    acknowledgement_override: Optional[SPEAcknowledgement] = None,
) -> SpotPricingEnvelope:
    ack = acknowledgement_override
    if ack is None and hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
        ack_db = spe_db.acknowledgement
        ack = SPEAcknowledgement(
            acknowledged_by_user_id=str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else "",
            acknowledged_at=ack_db.acknowledged_at,
            statement=ack_db.statement,
        )

    mgr = None
    if hasattr(spe_db, 'manager_approval') and spe_db.manager_approval:
        mgr_db = spe_db.manager_approval
        mgr = SPEManagerApproval(
            approved=mgr_db.approved,
            manager_user_id=str(mgr_db.manager_id) if mgr_db.manager_id else "",
            decision_at=mgr_db.decision_at,
            comment=mgr_db.comment,
        )

    charges = [
        SPEChargeLine(
            code=cl.code,
            description=cl.description,
            amount=float(cl.amount),
            currency=cl.currency,
            unit=cl.unit,
            bucket=cl.bucket,
            is_primary_cost=cl.is_primary_cost,
            conditional=cl.conditional,
            source_reference=cl.source_reference,
            entered_by_user_id=str(cl.entered_by_id) if cl.entered_by_id else "",
            entered_at=cl.entered_at,
        )
        for cl in spe_db.charge_lines.all()
    ]

    ctx = spe_db.shipment_context_json
    status_value = status_override or spe_db.status

    return SpotPricingEnvelope(
        id=str(spe_db.id),
        status=SPEStatus(status_value),
        shipment=SPEShipmentContext(
            origin_country=ctx.get('origin_country', 'OTHER'),
            destination_country=ctx.get('destination_country', 'OTHER'),
            origin_code=ctx.get('origin_code', 'XXX'),
            destination_code=ctx.get('destination_code', 'XXX'),
            commodity=ctx.get('commodity', 'GCR'),
            total_weight_kg=ctx.get('total_weight_kg', 1.0),
            pieces=ctx.get('pieces', 1),
            service_scope=str(ctx.get('service_scope', 'p2p')).lower(),
        ),
        charges=charges,
        conditions=SPEConditions(**spe_db.conditions_json) if spe_db.conditions_json else SPEConditions(),
        acknowledgement=ack,
        manager_approval=mgr,
        spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
        spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
        created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
        created_at=spe_db.created_at,
        expires_at=spe_db.expires_at,
    )


# =============================================================================
# SCOPE VALIDATION API
# =============================================================================

class SpotScopeValidateAPIView(APIView):
    """
    POST /api/v3/spot/validate-scope/
    
    Validate shipment is within PNG scope.
    Must be called BEFORE any SPOT logic.
    
    Request:
        { "origin_country": "AU", "destination_country": "PG" }
    
    Response:
        { "is_valid": true, "error": null }
        or
        { "is_valid": false, "error": "Out of scope: ..." }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        origin = request.data.get('origin_country', '')
        destination = request.data.get('destination_country', '')
        
        is_valid, error = ScopeValidator.validate(origin, destination)
        
        return Response({
            'is_valid': is_valid,
            'error': error,
        })


# =============================================================================
# TRIGGER EVALUATION API
# =============================================================================

class SpotTriggerEvaluateAPIView(APIView):
    """
    POST /api/v3/spot/evaluate-trigger/
    
    Evaluate if SPOT mode is required for shipment.
    
    Request:
        {
            "origin_country": "CN",
            "destination_country": "PG",
            "commodity": "GCR",
            "origin_airport": "SZX",
            "destination_airport": "POM",
            "has_valid_buy_rate": false
        }
    
    Response:
        {
            "is_spot_required": true,
            "trigger": {
                "code": "NO_BUY_RATE",
                "text": "No valid BUY rate exists..."
            }
        }
        or
        {
            "is_spot_required": false,
            "trigger": null
        }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Calculate direction
        origin_country = request.data.get('origin_country', '')
        destination_country = request.data.get('destination_country', '')
        
        if origin_country == 'PG' and destination_country == 'PG':
            direction = 'DOMESTIC'
        elif origin_country == 'PG':
            direction = 'EXPORT'
        else:
            direction = 'IMPORT'
        
        # Build component availability map from DB
        service_scope = request.data.get('service_scope', 'P2P')
        origin_airport = request.data.get('origin_airport', '')
        destination_airport = request.data.get('destination_airport', '')
        
        from quotes.spot_services import RateAvailabilityService
        component_availability = RateAvailabilityService.get_availability(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope
        )

        is_spot, trigger = SpotTriggerEvaluator.evaluate(
            origin_country=origin_country,
            destination_country=destination_country,
            direction=direction,
            service_scope=service_scope,
            component_availability=component_availability
        )
        
        return Response({
            'is_spot_required': is_spot,
            'trigger': {
                'code': trigger.code,
                'text': trigger.text,
                'missing_components': trigger.missing_components,
            } if trigger else None,
        })


# =============================================================================
# STANDARD CHARGES API (Hybrid SPOT)
# =============================================================================

class StandardChargesAPIView(APIView):
    """
    POST /api/v3/spot/standard-charges/
    
    Fetch standard charges from DB for hybrid SPOT pre-population.
    Returns airfreight and origin charges where DB coverage exists.
    
    Request:
        {
            "origin_code": "POM",
            "destination_code": "SIN",
            "direction": "EXPORT",
            "service_scope": "D2D",
            "weight_kg": 100,
            "commodity": "GCR"
        }
    
    Response:
        {
            "charges": [
                {
                    "code": "FREIGHT",
                    "description": "Airfreight",
                    "amount": "5.50",
                    "currency": "USD",
                    "unit": "per_kg",
                    "bucket": "airfreight",
                    "is_primary_cost": true,
                    "source_reference": "Standard Rate (ExportCOGS)"
                },
                ...
            ]
        }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        from quotes.spot_services import StandardChargeService
        
        origin_code = request.data.get("origin_code", "").upper()
        destination_code = request.data.get("destination_code", "").upper()
        direction = request.data.get("direction", "EXPORT").upper()
        service_scope = request.data.get("service_scope", "D2D").upper()
        weight_kg = float(request.data.get("weight_kg", 100))
        commodity = request.data.get("commodity", "GCR").upper()
        
        if not origin_code or not destination_code:
            return Response(
                {"error": "origin_code and destination_code are required"},
                status=400
            )
        
        charges = StandardChargeService.get_standard_charges(
            origin_code=origin_code,
            destination_code=destination_code,
            direction=direction,
            service_scope=service_scope,
            weight_kg=weight_kg,
            commodity=commodity,
        )
        
        return Response({"charges": charges})


# =============================================================================
# SPE LIFECYCLE APIs
# =============================================================================

class SpotEnvelopeListCreateAPIView(APIView):
    """
    GET  /api/v3/spot/envelopes/          - List user's SPEs
    POST /api/v3/spot/envelopes/          - Create new SPE
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List SPEs created by user."""
        spe_qs = SpotPricingEnvelopeDB.objects.all()
        if getattr(request.user, 'role', '') not in ['manager', 'admin']:
            spe_qs = spe_qs.filter(created_by=request.user)

        spes = spe_qs.order_by('-created_at')[:20]
        
        return Response([
            self._serialize_spe(spe) for spe in spes
        ])
    
    def post(self, request):
        """Create new SPE in DRAFT status."""
        with open("debug_spe.log", "a") as f:
            f.write(f"\n--- {timezone.now()} --- POST to envelopes ---\n")
            f.write(f"Data: {request.data}\n")
        try:
            data = request.data
            
            # Validate required fields
            required = ['shipment_context', 'trigger_code', 'trigger_text']
            for field in required:
                if field not in data:
                    return Response(
                        {'error': f'Missing required field: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create DB record
            ctx = data['shipment_context']
            now = timezone.now()
            validity_hours = data.get('validity_hours', 72)
            
            spe_db = SpotPricingEnvelopeDB.objects.create(
                status='draft',
                shipment_context_json=ctx,
                conditions_json=data.get('conditions', {}),
                spot_trigger_reason_code=data['trigger_code'],
                spot_trigger_reason_text=data['trigger_text'],
                created_by=request.user,
                expires_at=now + timedelta(hours=validity_hours),
            )
            
            # Create charge lines (optional)
            charges_data = data.get('charges', [])
            for charge in charges_data:
                SPEChargeLineDB.objects.create(
                    envelope=spe_db,
                    code=charge['code'],
                    description=charge['description'],
                    amount=charge['amount'],
                    currency=charge['currency'],
                    unit=charge['unit'],
                    bucket=charge['bucket'],
                    is_primary_cost=charge.get('is_primary_cost', False),
                    conditional=charge.get('conditional', False),
                    source_reference=charge['source_reference'],
                    entered_by=request.user,
                    entered_at=now,
                )
            
            # Validate via Pydantic (will raise if invalid)
            try:
                self._validate_spe(spe_db)
            except Exception as e:
                logger.error("Validation failed for SPE %s: %s", spe_db.id, str(e), exc_info=True)
                spe_db.delete()
                return Response(
                    {'error': f"Validation Error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info("Created SPE %s for user %s", spe_db.id, request.user.username)
            
            return Response(
                self._serialize_spe(spe_db),
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception("Unexpected error creating SPE")
            with open("debug_spe.log", "a") as f:
                import traceback
                f.write(f"ERROR: {str(e)}\n")
                f.write(traceback.format_exc())
            return Response(
                {'error': f"Internal Server Error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _serialize_spe(self, spe_db):
        """Serialize SPE DB to JSON."""
        missing_fields = _get_missing_mandatory_fields(spe_db)
        return {
            'id': str(spe_db.id),
            'status': spe_db.status,
            'shipment': spe_db.shipment_context_json,
            'conditions': spe_db.conditions_json,
            'spot_trigger_reason_code': spe_db.spot_trigger_reason_code,
            'spot_trigger_reason_text': spe_db.spot_trigger_reason_text,
            'created_at': spe_db.created_at.isoformat(),
            'expires_at': spe_db.expires_at.isoformat(),
            'is_expired': spe_db.is_expired,
            'has_acknowledgement': hasattr(spe_db, 'acknowledgement'),
            'missing_mandatory_fields': missing_fields,
            'can_proceed': len(missing_fields) == 0,
            'charges': [
                {
                    'id': str(cl.id),
                    'code': cl.code,
                    'description': cl.description,
                    'amount': str(cl.amount),
                    'currency': cl.currency,
                    'unit': cl.unit,
                    'bucket': cl.bucket,
                    'is_primary_cost': cl.is_primary_cost,
                    'conditional': cl.conditional,
                    'source_reference': cl.source_reference,
                }
                for cl in spe_db.charge_lines.all()
            ],
        }
    
    def _validate_spe(self, spe_db):
        """Validate SPE via Pydantic schemas."""
        ctx = spe_db.shipment_context_json
        charges = [
            SPEChargeLine(
                code=cl.code,
                description=cl.description,
                amount=float(cl.amount),
                currency=cl.currency,
                unit=cl.unit,
                bucket=cl.bucket,
                is_primary_cost=cl.is_primary_cost,
                conditional=cl.conditional,
                source_reference=cl.source_reference,
                entered_by_user_id=str(cl.entered_by_id) if cl.entered_by_id else "",
                entered_at=cl.entered_at,
            )
            for cl in spe_db.charge_lines.all()
        ]
        
        # This will raise ValueError if invalid
        SpotPricingEnvelope(
            id=str(spe_db.id),
            status=SPEStatus(spe_db.status),
            shipment=SPEShipmentContext(
                origin_country=ctx.get('origin_country', 'OTHER'),
                destination_country=ctx.get('destination_country', 'OTHER'),
                origin_code=ctx.get('origin_code', 'XXX'),
                destination_code=ctx.get('destination_code', 'XXX'),
                commodity=ctx.get('commodity', 'GCR'),
                total_weight_kg=ctx.get('total_weight_kg', 1.0),
                pieces=ctx.get('pieces', 1),
                service_scope=str(ctx.get('service_scope', 'p2p')).lower(),
            ),
            charges=charges,
            conditions=SPEConditions(**spe_db.conditions_json) if spe_db.conditions_json else SPEConditions(),
            spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
            spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
            created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
            created_at=spe_db.created_at,
            expires_at=spe_db.expires_at,
        )


class SpotEnvelopeDetailAPIView(APIView):
    """
    GET /api/v3/spot/envelopes/<id>/
    
    Get SPE details.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, envelope_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            SpotPricingEnvelopeDB.objects.prefetch_related(
                'charge_lines', 'acknowledgement', 'manager_approval'
            ),
        )
        
        return Response(self._serialize_spe(spe_db))
    
    def patch(self, request, envelope_id):
        """Update DRAFT SPE with new charges or conditions."""
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot update SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        data = request.data
        now = timezone.now()
        
        # Update conditions
        if 'conditions' in data:
            spe_db.conditions_json = data['conditions']
            
        # Update charges (replace all)
        if 'charges' in data:
            # Delete existing
            spe_db.charge_lines.all().delete()
            
            # Create new
            for charge in data['charges']:
                # Sanitize decimal fields
                amount_val = charge.get('amount')
                if amount_val == "":
                    amount_val = None
                    
                min_charge_val = charge.get('min_charge')
                if min_charge_val == "":
                    min_charge_val = None

                # Map Special Units
                unit_val = charge['unit']
                if unit_val == 'min_or_per_kg':
                    unit_val = 'per_kg'
                elif unit_val == 'flat': 
                    unit_val = 'flat' # Explicitly supported by model

                SPEChargeLineDB.objects.create(
                    envelope=spe_db,
                    code=charge['code'],
                    description=charge['description'],
                    amount=amount_val,
                    currency=charge['currency'],
                    unit=unit_val,        # Correct field: unit
                    bucket=charge['bucket'],
                    is_primary_cost=charge.get('is_primary_cost', False),
                    conditional=charge.get('conditional', False),
                    min_charge=min_charge_val,
                    note=charge.get('note') or "", # Correct field: note (singular)
                    source_reference=charge['source_reference'],
                    entered_by=request.user,
                    entered_at=now,
                )
        
        spe_db.save()
        
        return Response(self._serialize_spe(spe_db))

    def _serialize_spe(self, spe_db):
        """Full serialization including ack and approval."""
        ack = None
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            ack_db = spe_db.acknowledgement
            ack = {
                'acknowledged_by_user_id': str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else None,
                'acknowledged_at': ack_db.acknowledged_at.isoformat(),
                'statement': ack_db.statement,
            }
        
        approval = None
        if hasattr(spe_db, 'manager_approval') and spe_db.manager_approval:
            appr_db = spe_db.manager_approval
            approval = {
                'approved': appr_db.approved,
                'manager_user_id': str(appr_db.manager_id) if appr_db.manager_id else None,
                'decision_at': appr_db.decision_at.isoformat(),
                'comment': appr_db.comment,
            }
        
        return {
            'id': str(spe_db.id),
            'status': spe_db.status,
            'shipment': spe_db.shipment_context_json,
            'shipment_context_hash': spe_db.shipment_context_hash,
            'conditions': spe_db.conditions_json,
            'spot_trigger_reason_code': spe_db.spot_trigger_reason_code,
            'spot_trigger_reason_text': spe_db.spot_trigger_reason_text,
            'created_at': spe_db.created_at.isoformat(),
            'expires_at': spe_db.expires_at.isoformat(),
            'is_expired': spe_db.is_expired,
            'context_integrity_valid': spe_db.verify_context_integrity(),
            'acknowledgement': ack,
            'manager_approval': approval,
            'missing_mandatory_fields': _get_missing_mandatory_fields(spe_db),
            'can_proceed': len(_get_missing_mandatory_fields(spe_db)) == 0,
            'charges': [
                {
                    'id': str(cl.id),
                    'code': cl.code,
                    'description': cl.description,
                    'amount': str(cl.amount),
                    'currency': cl.currency,
                    'unit': cl.unit,
                    'bucket': cl.bucket,
                    'is_primary_cost': cl.is_primary_cost,
                    'conditional': cl.conditional,
                    'min_charge': str(cl.min_charge) if cl.min_charge is not None else None,
                    'note': cl.note,
                    'exclude_from_totals': cl.exclude_from_totals,
                    'percentage_basis': cl.percentage_basis,
                    'source_reference': cl.source_reference,
                }
                for cl in spe_db.charge_lines.all()
            ],
        }


class SpotEnvelopeAcknowledgeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/acknowledge/
    
    Add Sales acknowledgement to SPE.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot acknowledge SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            return Response(
                {'error': 'SPE already acknowledged'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        temp_ack = SPEAcknowledgement(
            acknowledged_by_user_id=str(request.user.id),
            acknowledged_at=timezone.now(),
            statement=SPEAcknowledgementDB.ACKNOWLEDGEMENT_STATEMENT,
        )

        try:
            status_override = 'ready'
            spe = _build_spe_from_db(
                spe_db,
                status_override=status_override,
                acknowledgement_override=temp_ack,
            )
        except ValueError as e:
            return Response(
                {'error': f'Validation Error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if spe.is_expired:
            return Response(
                {'error': 'SPE has expired and cannot be acknowledged.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Always validate for pricing (no manager approval required)
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        if not is_valid:
            return Response(
                {'error': error},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create acknowledgement
        SPEAcknowledgementDB.objects.create(
            envelope=spe_db,
            acknowledged_by=request.user,
            acknowledged_at=temp_ack.acknowledged_at,
            statement=temp_ack.statement,
        )

        # Always transition to ready - no manager approval required
        spe_db.status = 'ready'
        spe_db.save()
        
        spe_db.refresh_from_db()
        
        logger.info("SPE %s acknowledged by %s", spe_db.id, request.user.username)
        
        return Response({
            'success': True,
            'status': spe_db.status,
        })


class SpotEnvelopeApproveAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/approve/
    
    Manager approval for SPE.
    
    Request:
        { "approved": true, "comment": "Looks good" }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        # Check user has manager role
        user_role = getattr(request.user, 'role', 'sales')
        if user_role not in ['manager', 'admin', 'owner']:
            return Response(
                {'error': 'Only managers can approve SPEs'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if hasattr(spe_db, 'manager_approval') and spe_db.manager_approval:
            return Response(
                {'error': 'SPE already has manager decision'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        approved = request.data.get('approved', False)
        comment = request.data.get('comment', '')
        
        # Create approval
        SPEManagerApprovalDB.objects.create(
            envelope=spe_db,
            approved=approved,
            manager=request.user,
            decision_at=timezone.now(),
            comment=comment,
        )
        
        # Update SPE status
        spe_db.status = 'ready' if approved else 'rejected'
        spe_db.save()
        
        logger.info(
            "SPE %s %s by manager %s",
            spe_db.id,
            'approved' if approved else 'rejected',
            request.user.username
        )
        
        return Response({
            'success': True,
            'status': spe_db.status,
            'approved': approved,
        })


class SpotEnvelopeComputeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/compute/
    
    Compute quote using SPE charges via pricing_v4 adapter.
    
    Request:
        { "quote_request": { ... standard quote fields ... } }
    
    Response:
        { ... quote result with pricing_mode: "SPOT" ... }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        from pricing_v4.adapter import PricingServiceV4Adapter
        from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            SpotPricingEnvelopeDB.objects.prefetch_related(
                'charge_lines', 'acknowledgement', 'manager_approval'
            ),
        )
        
        # Build Pydantic SPE for validation
        try:
            spe = _build_spe_from_db(spe_db)
        except ValueError as e:
            return Response(
                {'error': f'Invalid SPE: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate SPE is ready for pricing
        from quotes.spot_services import SpotEnvelopeService
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        if not is_valid:
            return Response(
                {'is_complete': False, 'reason': error},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build quote input from request
        quote_data = request.data.get('quote_request', {})
        ctx = spe_db.shipment_context_json
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response(
                {'error': f'Location not found: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine shipment type
        origin_country = ctx.get('origin_country')
        dest_country = ctx.get('destination_country')
        if origin_country == 'PG' and dest_country == 'PG':
            shipment_type = 'DOMESTIC'
        elif origin_country == 'PG':
            shipment_type = 'EXPORT'
        else:
            shipment_type = 'IMPORT'
        
        from datetime import date
        
        origin_ref = LocationRef(
            id=origin_loc.id,
            code=origin_loc.code,
            name=origin_loc.name,
            country_code=origin_loc.country.code if origin_loc.country else None,
            currency_code=origin_loc.country.currency.code if origin_loc.country and origin_loc.country.currency else None,
        )
        dest_ref = LocationRef(
            id=dest_loc.id,
            code=dest_loc.code,
            name=dest_loc.name,
            country_code=dest_loc.country.code if dest_loc.country else None,
            currency_code=dest_loc.country.currency.code if dest_loc.country and dest_loc.country.currency else None,
        )

        shipment = ShipmentDetails(
            mode='AIR',
            shipment_type=shipment_type,
            incoterm=quote_data.get('incoterm', 'DAP'),
            payment_term=quote_data.get('payment_term', 'PREPAID'),
            is_dangerous_goods=ctx.get('commodity') == 'DG',
            pieces=[
                Piece(
                    pieces=ctx.get('pieces', 1),
                    length_cm=0,
                    width_cm=0,
                    height_cm=0,
                    gross_weight_kg=ctx.get('total_weight_kg', 0) / max(ctx.get('pieces', 1), 1),
                )
            ],
            service_scope=quote_data.get('service_scope', 'D2D'),
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        quote_input = QuoteInput(
            customer_id=getattr(spe_db.quote, 'customer_id', None) or uuid.uuid4(),
            contact_id=getattr(spe_db.quote, 'contact_id', None) or uuid.uuid4(),
            shipment=shipment,
            quote_date=date.today(),
            output_currency=quote_data.get('output_currency', 'PGK'),
        )
        
        # Call adapter with spot_envelope_id
        adapter = PricingServiceV4Adapter(
            quote_input=quote_input,
            spot_envelope_id=UUID(str(spe_db.id))
        )
        
        try:
            result = adapter.calculate_charges()
        except ValueError as e:
            logger.error(f"Compute failed with ValueError: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get FX rate info for display
        fx_info = None
        if adapter.fx_snapshot:
            # Find the charge currency from SPE charges (usually the first one)
            spe_charges = list(spe_db.charge_lines.all())
            if spe_charges:
                charge_currency = spe_charges[0].currency
                if charge_currency != 'PGK':
                    fx_rates_dict = adapter._get_fx_rates_dict()
                    fx_buy_rate = adapter._get_fx_buy_rate(charge_currency, fx_rates_dict)
                    fx_info = {
                        'source_currency': charge_currency,
                        'target_currency': 'PGK',
                        'rate': str(fx_buy_rate),
                        'as_of': adapter.fx_snapshot.as_of_timestamp.isoformat() if adapter.fx_snapshot.as_of_timestamp else None,
                    }
        
        return Response({
            'is_complete': True,
            'pricing_mode': adapter.get_pricing_mode(),
            'spe_id': str(spe_db.id),
            'fx_info': fx_info,
            'lines': [
                {
                    'code': line.service_component_code,
                    'description': line.service_component_desc,
                    'cost_pgk': str(line.cost_pgk),
                    'sell_pgk': str(line.sell_pgk),
                    'sell_pgk_incl_gst': str(line.sell_pgk_incl_gst),
                    'leg': line.leg,
                    'source': line.cost_source,
                    'is_informational': getattr(line, 'is_informational', False),
                    'bucket': line.bucket,
                }
                for line in result.lines
            ],
            'totals': {
                'total_cost_pgk': str(result.totals.total_cost_pgk),
                'total_sell_pgk': str(result.totals.total_sell_pgk),
                'total_sell_pgk_incl_gst': str(result.totals.total_sell_pgk_incl_gst),
            },
        })
    
class SpotReplyAnalysisAPIView(APIView):
    """
    POST /api/v3/spot/analyze-reply/
    
    Analyze agent rate reply text and return assertions.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        text = request.data.get('text', '')
        spe_id = request.data.get('spe_id')
        manual_assertions = request.data.get('assertions', [])
        use_ai = request.data.get('use_ai', True)
        
        if not text:
            return Response(
                {'error': 'No text provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        shipment_context = None
        if spe_id:
            try:
                spe_db = _get_spe_or_404(request.user, spe_id)
                shipment_context = spe_db.shipment_context_json
            except (SpotPricingEnvelopeDB.DoesNotExist, ValueError):
                pass
            
        if shipment_context:
            # Enrich with real names for the AI prompt
            from core.models import Airport
            orig_ap = Airport.objects.filter(iata_code=shipment_context.get('origin_code')).first()
            dest_ap = Airport.objects.filter(iata_code=shipment_context.get('destination_code')).first()
            if orig_ap: shipment_context['origin'] = orig_ap.city.name
            if dest_ap: shipment_context['destination'] = dest_ap.city.name
            
        # Calculate direction and availability to guide the analyst
        direction = 'IMPORT'
        availability = None
        if shipment_context:
            origin_country = shipment_context.get('origin_country', '')
            destination_country = shipment_context.get('destination_country', '')
            if origin_country == 'PG' and destination_country == 'PG':
                direction = 'DOMESTIC'
            elif origin_country == 'PG':
                direction = 'EXPORT'
            else:
                direction = 'IMPORT'
            
            from quotes.spot_services import RateAvailabilityService
            availability = RateAvailabilityService.get_availability(
                origin_airport=shipment_context.get('origin_code', ''),
                destination_airport=shipment_context.get('destination_code', ''),
                direction=direction,
                service_scope=shipment_context.get('service_scope', 'P2P')
            )
            
            # Enrich context with missing status to guide AI
            if availability:
                shipment_context['missing_components'] = [k for k, v in availability.items() if not v]

        if use_ai and not manual_assertions:
            # If AI is requested and no manual edits provided, do full AI analysis
            result = ReplyAnalysisService.analyze_with_ai(
                raw_text=text,
                shipment_context=shipment_context,
                availability=availability
            )
        else:
            # Manual edit flow or fallback
            result = ReplyAnalysisService.analyze_manual(
                raw_text=text,
                assertions=manual_assertions
            )
        
        return Response(result.model_dump())

# Add this to the end of spot_views.py

class SpotEnvelopeCreateQuoteAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/create-quote/
    
    Convert SPE to a formal Quote (v3).
    Creates Quote, QuoteVersion, QuoteLines, and QuoteTotals.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        from pricing_v4.adapter import PricingServiceV4Adapter
        from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal, ServiceComponent
        from parties.models import Company, Contact
        from uuid import UUID
        from datetime import date
        
        spe_db = _get_spe_or_404(
            request.user, 
            envelope_id,
            SpotPricingEnvelopeDB.objects.prefetch_related('charge_lines', 'acknowledgement', 'manager_approval')
        )
        
        # --- 1. Re-run Computation (Same as ComputeView) ---
        # Note: Ideally this setup logic should be shared, but duplicating for safety now.
        
        try:
            spe = _build_spe_from_db(spe_db)
        except ValueError as e:
            return Response({'error': f'Invalid SPE: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        quote_data = request.data.get('quote_request', {})
        ctx = spe_db.shipment_context_json
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response({'error': f'Location not found: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        origin_country = ctx.get('origin_country')
        dest_country = ctx.get('destination_country')
        if origin_country == 'PG' and dest_country == 'PG':
            shipment_type = 'DOMESTIC'
        elif origin_country == 'PG':
            shipment_type = 'EXPORT'
        else:
            shipment_type = 'IMPORT'
            
        origin_ref = LocationRef(
            id=origin_loc.id, code=origin_loc.code, name=origin_loc.name,
            country_code=origin_loc.country.code if origin_loc.country else None,
            currency_code=origin_loc.country.currency.code if origin_loc.country and origin_loc.country.currency else None,
        )
        dest_ref = LocationRef(
            id=dest_loc.id, code=dest_loc.code, name=dest_loc.name,
            country_code=dest_loc.country.code if dest_loc.country else None,
            currency_code=dest_loc.country.currency.code if dest_loc.country and dest_loc.country.currency else None,
        )

        shipment = ShipmentDetails(
            mode='AIR',
            shipment_type=shipment_type,
            incoterm=quote_data.get('incoterm', 'DAP'),
            payment_term=quote_data.get('payment_term', 'PREPAID'),
            is_dangerous_goods=ctx.get('commodity') == 'DG',
            pieces=[Piece(
                pieces=ctx.get('pieces', 1),
                length_cm=0, width_cm=0, height_cm=0,
                gross_weight_kg=ctx.get('total_weight_kg', 0) / max(ctx.get('pieces', 1), 1),
            )],
            service_scope=quote_data.get('service_scope', 'D2D'),
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        # Ensure customer/contact logic
        cust_id = None
        cont_id = None
        
        if spe_db.quote:
            cust_id = spe_db.quote.customer_id
            cont_id = spe_db.quote.contact_id

        if not cust_id:
             req_cust = request.data.get('customer_id')
             if req_cust:
                 cust_id = UUID(req_cust)
             else:
                 # Last resort: Try "Cash Customer" or similar
                 cust = Company.objects.first()
                 if cust: cust_id = cust.id
        
        if not cust_id:
            return Response({'error': 'Customer required to create quote'}, status=status.HTTP_400_BAD_REQUEST)

        # Create QuoteInput
        # Note: If QuoteInput enforces contact_id is not None, we might need to fake it if cont_id is None.
        # But generally, for Spot, we just need basic input.
        # Check if QuoteInput accepts None. If not, we use cust_id as placeholder for logic ONLY, but NOT for DB.
        
        qi_contact_id = cont_id if cont_id else cust_id # Placeholder for computation if needed
        
        quote_input = QuoteInput(
            customer_id=cust_id,
            contact_id=qi_contact_id, 
            shipment=shipment,
            quote_date=date.today(),
            output_currency=quote_data.get('output_currency', 'PGK'),
        )
        
        adapter = PricingServiceV4Adapter(quote_input=quote_input, spot_envelope_id=UUID(str(spe_db.id)))
        
        try:
            result = adapter.calculate_charges()
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # --- 2. Create/Update Quote ---
        if spe_db.quote:
            quote = spe_db.quote
            # Update fields?
            # quote.status = Quote.Status.DRAFT 
            # quote.save()
        else:
            quote = Quote.objects.create(
                customer_id=cust_id,
                contact_id=cont_id, # FIX: Pass actual contact ID (can be None)
                origin_location=origin_loc,
                destination_location=dest_loc,
                shipment_type=shipment_type,
                mode='AIR',
                incoterm=shipment.incoterm,
                payment_term=shipment.payment_term,
                service_scope=shipment.service_scope,
                output_currency=quote_input.output_currency,
                is_dangerous_goods=shipment.is_dangerous_goods,
                created_by=request.user,
                status=Quote.Status.DRAFT,
                request_details_json=quote_input.model_dump(mode='json'),
            )
            spe_db.quote = quote
            spe_db.save()

        # --- 3. Create Version ---
        # Determine version number
        last_version = quote.versions.order_by('-version_number').first()
        new_v_num = (last_version.version_number + 1) if last_version else 1
        
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=new_v_num,
            status=Quote.Status.DRAFT,
            created_by=request.user,
            payload_json=quote_input.model_dump(mode='json'),
            reason="Created from SPOT Envelope"
        )
        
        # --- 4. Save Lines ---
        
        for line_data in result.lines:
            # Resolve Component ID
            sc = None
            if line_data.service_component_id:
                try:
                    sc = ServiceComponent.objects.get(id=line_data.service_component_id)
                except ServiceComponent.DoesNotExist:
                    pass
            
            QuoteLine.objects.create(
                quote_version=version,
                service_component=sc,
                cost_pgk=line_data.cost_pgk,
                cost_fcy=line_data.cost_fcy,
                cost_fcy_currency=line_data.cost_fcy_currency,
                sell_pgk=line_data.sell_pgk,
                sell_pgk_incl_gst=line_data.sell_pgk_incl_gst,
                sell_fcy=line_data.sell_fcy,
                sell_fcy_incl_gst=line_data.sell_fcy_incl_gst,
                sell_fcy_currency=line_data.sell_fcy_currency,
                exchange_rate=line_data.exchange_rate,
                cost_source=line_data.cost_source,
                cost_source_description=line_data.cost_source_description,
                is_rate_missing=line_data.is_rate_missing,
                is_informational=getattr(line_data, 'is_informational', False)
            )

        # --- 5. Save Totals ---
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=result.totals.total_cost_pgk,
            total_sell_pgk=result.totals.total_sell_pgk,
            total_sell_pgk_incl_gst=result.totals.total_sell_pgk_incl_gst,
            total_sell_fcy=result.totals.total_sell_fcy,
            total_sell_fcy_incl_gst=result.totals.total_sell_fcy_incl_gst,
            total_sell_fcy_currency=result.totals.total_sell_fcy_currency,
            has_missing_rates=result.totals.has_missing_rates,
            notes=result.totals.notes
        )
        
        return Response({
            'success': True,
            'quote_id': str(quote.id),
            'quote_number': quote.quote_number
        })
