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
from datetime import datetime, timedelta
from uuid import UUID

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.shortcuts import get_object_or_404

from quotes.spot_services import (
    ScopeValidator,
    SpotTriggerEvaluator,
    SpotEnvelopeService,
    SpotApprovalPolicy,
    SpotTriggerReason,
    TriggerResult,
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
        is_spot, trigger = SpotTriggerEvaluator.evaluate(
            origin_country=request.data.get('origin_country', ''),
            destination_country=request.data.get('destination_country', ''),
            commodity=request.data.get('commodity', 'GCR'),
            origin_airport=request.data.get('origin_airport'),
            destination_airport=request.data.get('destination_airport'),
            has_valid_buy_rate=request.data.get('has_valid_buy_rate', True),
            has_valid_cogs=request.data.get('has_valid_cogs', True),
            has_valid_sell=request.data.get('has_valid_sell', True),
            is_multi_leg=request.data.get('is_multi_leg', False),
        )
        
        return Response({
            'is_spot_required': is_spot,
            'trigger': {
                'code': trigger.code,
                'text': trigger.text,
            } if trigger else None,
        })


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
        spes = SpotPricingEnvelopeDB.objects.filter(
            created_by=request.user
        ).order_by('-created_at')[:20]
        
        return Response([
            self._serialize_spe(spe) for spe in spes
        ])
    
    def post(self, request):
        """Create new SPE in DRAFT status."""
        data = request.data
        
        # Validate required fields
        required = ['shipment_context', 'charges', 'trigger_code', 'trigger_text']
        for field in required:
            if field not in data:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Create DB record
        ctx = data['shipment_context']
        now = datetime.now()
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
        
        # Create charge lines
        for charge in data['charges']:
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
        except ValueError as e:
            spe_db.delete()
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info("Created SPE %s for user %s", spe_db.id, request.user.username)
        
        return Response(
            self._serialize_spe(spe_db),
            status=status.HTTP_201_CREATED
        )
    
    def _serialize_spe(self, spe_db):
        """Serialize SPE DB to JSON."""
        return {
            'id': str(spe_db.id),
            'status': spe_db.status,
            'shipment_context': spe_db.shipment_context_json,
            'conditions': spe_db.conditions_json,
            'trigger_code': spe_db.spot_trigger_reason_code,
            'trigger_text': spe_db.spot_trigger_reason_text,
            'created_at': spe_db.created_at.isoformat(),
            'expires_at': spe_db.expires_at.isoformat(),
            'is_expired': spe_db.is_expired,
            'has_acknowledgement': hasattr(spe_db, 'acknowledgement'),
            'has_manager_approval': hasattr(spe_db, 'manager_approval'),
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
        spe_db = get_object_or_404(
            SpotPricingEnvelopeDB.objects.prefetch_related(
                'charge_lines', 'acknowledgement', 'manager_approval'
            ),
            id=envelope_id
        )
        
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
            'shipment_context': spe_db.shipment_context_json,
            'shipment_context_hash': spe_db.shipment_context_hash,
            'conditions': spe_db.conditions_json,
            'trigger_code': spe_db.spot_trigger_reason_code,
            'trigger_text': spe_db.spot_trigger_reason_text,
            'created_at': spe_db.created_at.isoformat(),
            'expires_at': spe_db.expires_at.isoformat(),
            'is_expired': spe_db.is_expired,
            'context_integrity_valid': spe_db.verify_context_integrity(),
            'acknowledgement': ack,
            'manager_approval': approval,
            'requires_manager_approval': SpotApprovalPolicy.requires_manager_approval(
                commodity=spe_db.shipment_context_json.get('commodity', 'GCR'),
                margin_percent=None,
                is_multi_leg=spe_db.spot_trigger_reason_code == SpotTriggerReason.MULTI_LEG_ROUTING,
            ),
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


class SpotEnvelopeAcknowledgeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/acknowledge/
    
    Add Sales acknowledgement to SPE.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        spe_db = get_object_or_404(SpotPricingEnvelopeDB, id=envelope_id)
        
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
        
        # Create acknowledgement
        SPEAcknowledgementDB.objects.create(
            envelope=spe_db,
            acknowledged_by=request.user,
            acknowledged_at=datetime.now(),
            statement="I acknowledge this is a conditional SPOT quote and not guaranteed",
        )
        
        # Check if we can transition to READY
        requires_approval = SpotApprovalPolicy.requires_manager_approval(
            commodity=spe_db.shipment_context_json.get('commodity', 'GCR'),
            margin_percent=None,
            is_multi_leg=spe_db.spot_trigger_reason_code == SpotTriggerReason.MULTI_LEG_ROUTING,
        )
        
        if not requires_approval:
            spe_db.status = 'ready'
            spe_db.save()
        
        spe_db.refresh_from_db()
        
        logger.info("SPE %s acknowledged by %s", spe_db.id, request.user.username)
        
        return Response({
            'success': True,
            'status': spe_db.status,
            'requires_manager_approval': requires_approval,
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
        spe_db = get_object_or_404(SpotPricingEnvelopeDB, id=envelope_id)
        
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
            decision_at=datetime.now(),
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
        from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentInput, PieceInput
        from core.models import Location
        
        spe_db = get_object_or_404(
            SpotPricingEnvelopeDB.objects.prefetch_related(
                'charge_lines', 'acknowledgement', 'manager_approval'
            ),
            id=envelope_id
        )
        
        # Build Pydantic SPE for validation
        try:
            spe = self._build_spe(spe_db)
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
        
        shipment = ShipmentInput(
            origin_location=origin_loc,
            destination_location=dest_loc,
            shipment_type=shipment_type,
            payment_term=quote_data.get('payment_term', 'PREPAID'),
            service_scope=quote_data.get('service_scope', 'D2D'),
            is_dangerous_goods=ctx.get('commodity') == 'DG',
            pieces=[
                PieceInput(
                    pieces=ctx.get('pieces', 1),
                    length_cm=0,
                    width_cm=0,
                    height_cm=0,
                    gross_weight_kg=ctx.get('total_weight_kg', 0) / max(ctx.get('pieces', 1), 1),
                )
            ],
        )
        
        quote_input = QuoteInput(
            shipment=shipment,
            quote_date=date.today(),
            output_currency=quote_data.get('output_currency', 'PGK'),
        )
        
        # Call adapter with spot_envelope_id
        adapter = PricingServiceV4Adapter(
            quote_input=quote_input,
            spot_envelope_id=UUID(str(spe_db.id))
        )
        
        result = adapter.calculate_charges()
        
        return Response({
            'is_complete': True,
            'pricing_mode': adapter.get_pricing_mode(),
            'spe_id': str(spe_db.id),
            'lines': [
                {
                    'code': line.service_component_code,
                    'description': line.service_component_desc,
                    'cost_pgk': str(line.cost_pgk),
                    'sell_pgk': str(line.sell_pgk),
                    'sell_pgk_incl_gst': str(line.sell_pgk_incl_gst),
                    'leg': line.leg,
                    'source': line.cost_source,
                }
                for line in result.lines
            ],
            'totals': {
                'total_cost_pgk': str(result.totals.total_cost_pgk),
                'total_sell_pgk': str(result.totals.total_sell_pgk),
                'total_sell_pgk_incl_gst': str(result.totals.total_sell_pgk_incl_gst),
            },
        })
    
    def _build_spe(self, spe_db):
        """Build Pydantic SPE from DB."""
        ctx = spe_db.shipment_context_json
        
        ack = None
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            ack_db = spe_db.acknowledgement
            ack = SPEAcknowledgement(
                acknowledged_by_user_id=str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else "",
                acknowledged_at=ack_db.acknowledged_at,
                statement="I acknowledge this is a conditional SPOT quote and not guaranteed",
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
        
        return SpotPricingEnvelope(
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
