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
import json
import uuid
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID

from django.utils import timezone
from django.db import transaction

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPESourceBatchDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
    SPEManagerApprovalDB,
)
from quotes.serializers import SpotPricingEnvelopeSerializer
from quotes.selectors import get_quote_for_user
from quotes.currency_rules import determine_quote_currency


logger = logging.getLogger(__name__)


def _user_is_manager_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_manager", False) or getattr(user, "is_admin", False):
        return True
    return getattr(user, "role", None) in ("manager", "admin")


def _user_can_access_spe(user, spe_db: SpotPricingEnvelopeDB) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _user_is_manager_or_admin(user):
        return True
    return spe_db.created_by_id == user.id


def _get_spe_or_404(user, envelope_id, queryset=None):
    spe_db = get_object_or_404(queryset or SpotPricingEnvelopeDB, id=envelope_id)
    if not _user_can_access_spe(user, spe_db):
        raise PermissionDenied("You do not have access to this SPOT envelope.")
    return spe_db


def _spe_queryset():
    return SpotPricingEnvelopeDB.objects.prefetch_related(
        'charge_lines__source_batch',
        'source_batches__charge_lines',
        'acknowledgement',
        'manager_approval',
    )


def _resolve_country_pair(
    origin_country: Optional[str],
    destination_country: Optional[str],
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
) -> tuple[str, str]:
    return ScopeValidator.normalize_countries(
        origin_country=origin_country,
        destination_country=destination_country,
        origin_airport=origin_code,
        destination_airport=destination_code,
    )


def _normalize_shipment_context(ctx: dict) -> dict:
    normalized = dict(ctx or {})
    origin_code = str(normalized.get("origin_code") or "").upper()
    destination_code = str(normalized.get("destination_code") or "").upper()
    origin_country, destination_country = _resolve_country_pair(
        normalized.get("origin_country"),
        normalized.get("destination_country"),
        origin_code=origin_code,
        destination_code=destination_code,
    )
    normalized["origin_code"] = origin_code
    normalized["destination_code"] = destination_code
    normalized["origin_country"] = origin_country
    normalized["destination_country"] = destination_country
    payment_term = str(normalized.get("payment_term") or "").strip().upper()
    if payment_term in {"PREPAID", "COLLECT"}:
        normalized["payment_term"] = payment_term
    elif "payment_term" in normalized:
        normalized.pop("payment_term", None)
    return normalized


def _normalize_source_kind(value: Optional[str]) -> str:
    normalized = str(value or SPESourceBatchDB.SourceKind.AGENT).strip().upper()
    valid = {choice for choice, _ in SPESourceBatchDB.SourceKind.choices}
    return normalized if normalized in valid else SPESourceBatchDB.SourceKind.OTHER


def _normalize_source_type(value: Optional[str], pdf_file=None) -> str:
    if pdf_file is not None:
        return SPESourceBatchDB.SourceType.PDF
    normalized = str(value or SPESourceBatchDB.SourceType.TEXT).strip().upper()
    valid = {choice for choice, _ in SPESourceBatchDB.SourceType.choices}
    return normalized if normalized in valid else SPESourceBatchDB.SourceType.TEXT


def _normalize_target_bucket(value: Optional[str]) -> str:
    normalized = str(value or SPESourceBatchDB.TargetBucket.MIXED).strip().lower()
    valid = {choice for choice, _ in SPESourceBatchDB.TargetBucket.choices}
    return normalized if normalized in valid else SPESourceBatchDB.TargetBucket.MIXED


def _default_source_label(source_kind: str, target_bucket: str) -> str:
    bucket_labels = {
        SPESourceBatchDB.TargetBucket.AIRFREIGHT: "Freight Source",
        SPESourceBatchDB.TargetBucket.ORIGIN_CHARGES: "Origin Charges Source",
        SPESourceBatchDB.TargetBucket.DESTINATION_CHARGES: "Destination Charges Source",
        SPESourceBatchDB.TargetBucket.MIXED: "Primary SPOT Source",
    }
    kind_prefix = {
        SPESourceBatchDB.SourceKind.AIRLINE: "Airline",
        SPESourceBatchDB.SourceKind.AGENT: "Agent",
        SPESourceBatchDB.SourceKind.MANUAL: "Manual",
        SPESourceBatchDB.SourceKind.OTHER: "Other",
    }
    return f"{kind_prefix.get(source_kind, 'Other')} {bucket_labels.get(target_bucket, 'Source')}"


def _get_or_create_source_batch(
    *,
    spe_db: SpotPricingEnvelopeDB,
    request,
    source_batch_id: Optional[str],
    source_kind: str,
    source_type: str,
    target_bucket: str,
    label: str,
    source_reference: str,
    raw_text: str,
    file_name: str = "",
    file_content_type: str = "",
    analysis_summary_json: Optional[dict] = None,
) -> SPESourceBatchDB:
    batch = None
    if source_batch_id:
        batch = get_object_or_404(spe_db.source_batches, id=source_batch_id)
    else:
        batch = (
            spe_db.source_batches
            .filter(
                source_kind=source_kind,
                target_bucket=target_bucket,
                label=label,
            )
            .order_by('-updated_at')
            .first()
        )
        if batch is None:
            batch = SPESourceBatchDB.objects.create(
                envelope=spe_db,
                source_kind=source_kind,
                source_type=source_type,
                target_bucket=target_bucket,
                label=label,
                source_reference=source_reference,
                raw_text=raw_text,
                file_name=file_name,
                file_content_type=file_content_type,
                analysis_summary_json=analysis_summary_json or {},
                created_by=request.user,
            )
            return batch

    batch.source_kind = source_kind
    batch.source_type = source_type
    batch.target_bucket = target_bucket
    batch.label = label
    batch.source_reference = source_reference
    batch.raw_text = raw_text
    batch.file_name = file_name
    batch.file_content_type = file_content_type
    batch.analysis_summary_json = analysis_summary_json or {}
    batch.save(
        update_fields=[
            'source_kind', 'source_type', 'target_bucket', 'label',
            'source_reference', 'raw_text', 'file_name', 'file_content_type',
            'analysis_summary_json', 'updated_at',
        ]
    )
    return batch


def _resolve_output_currency_for_shipment(
    shipment_type: str,
    payment_term: str,
    origin_location,
    destination_location,
) -> str:
    return determine_quote_currency(
        shipment_type=shipment_type,
        payment_term=payment_term,
        origin_country_code=getattr(origin_location, "country_code", None),
        destination_country_code=getattr(destination_location, "country_code", None),
    )


def _normalize_missing_components(raw_value) -> Optional[list[str]]:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        raw_list = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_list = list(raw_value)
    else:
        return []
    return [str(item).upper() for item in raw_list if str(item).strip()]


def _derive_missing_components_from_context(ctx: dict) -> Optional[list[str]]:
    origin_code = str(ctx.get("origin_code") or "").upper()
    destination_code = str(ctx.get("destination_code") or "").upper()
    if not origin_code or not destination_code:
        return None

    service_scope = str(ctx.get("service_scope") or "P2P")
    payment_term = str(ctx.get("payment_term") or "").upper() or None
    origin_country, destination_country = _resolve_country_pair(
        ctx.get("origin_country"),
        ctx.get("destination_country"),
        origin_code=origin_code,
        destination_code=destination_code,
    )
    direction = _infer_shipment_type(origin_country, destination_country)

    try:
        from quotes.spot_services import RateAvailabilityService
        from quotes.completeness import evaluate_from_availability

        availability = RateAvailabilityService.get_availability(
            origin_airport=origin_code,
            destination_airport=destination_code,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
        )
        coverage = evaluate_from_availability(
            component_availability=availability,
            shipment_type=direction,
            service_scope=service_scope,
        )
        return coverage.missing_required
    except Exception:
        logger.exception(
            "Failed deriving missing components for SPOT context %s->%s",
            origin_code,
            destination_code,
        )
        return None


def _resolve_missing_components_for_context(ctx: dict) -> Optional[list[str]]:
    normalized = _normalize_missing_components(ctx.get("missing_components"))
    if normalized is not None:
        return normalized
    return _derive_missing_components_from_context(ctx)


def _infer_shipment_type(origin_country: str, destination_country: str) -> str:
    if origin_country == "PG" and destination_country == "PG":
        return "DOMESTIC"
    if origin_country == "PG":
        return "EXPORT"
    return "IMPORT"


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

    charges = []
    for cl in spe_db.charge_lines.all():
        # Guard against legacy/invalid draft rows with zero amount.
        # SPE schema requires amount > 0 and these rows should not block acknowledgement.
        if cl.amount is None or cl.amount <= 0:
            logger.warning(
                "Skipping invalid SPE charge line with non-positive amount: spe=%s line=%s amount=%s",
                spe_db.id,
                cl.id,
                cl.amount,
            )
            continue

        charges.append(
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
                min_charge=float(cl.min_charge) if cl.min_charge is not None else None,
                note=cl.note,
                exclude_from_totals=cl.exclude_from_totals,
                percentage_basis=cl.percentage_basis,
                calculation_type=cl.calculation_type,
                unit_type=cl.unit_type,
                rate=float(cl.rate) if cl.rate is not None else None,
                min_amount=float(cl.min_amount) if cl.min_amount is not None else None,
                max_amount=float(cl.max_amount) if cl.max_amount is not None else None,
                percent=float(cl.percent) if cl.percent is not None else None,
                percent_basis=cl.percent_basis,
                rule_meta=cl.rule_meta or {},
            )
        )

    ctx = _normalize_shipment_context(spe_db.shipment_context_json)
    if not ctx.get("payment_term") and getattr(spe_db, "quote", None) and getattr(spe_db.quote, "payment_term", None):
        ctx["payment_term"] = str(spe_db.quote.payment_term).upper()
    resolved_missing_components = _resolve_missing_components_for_context(ctx)
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
            payment_term=(str(ctx.get('payment_term')).lower() if ctx.get('payment_term') else None),
            missing_components=resolved_missing_components,
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
        origin_code = request.data.get('origin_code', '')
        destination_code = request.data.get('destination_code', '')
        
        is_valid, error = ScopeValidator.validate(
            origin,
            destination,
            origin_airport=origin_code,
            destination_airport=destination_code,
        )
        
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
        origin_airport = request.data.get('origin_airport', '')
        destination_airport = request.data.get('destination_airport', '')
        origin_country, destination_country = _resolve_country_pair(
            request.data.get('origin_country', ''),
            request.data.get('destination_country', ''),
            origin_code=origin_airport,
            destination_code=destination_airport,
        )
        direction = _infer_shipment_type(origin_country, destination_country)
        
        # Build component availability map from DB
        service_scope = request.data.get('service_scope', 'P2P')
        payment_term = str(request.data.get('payment_term') or '').upper()
        if payment_term not in {'PREPAID', 'COLLECT'}:
            return Response(
                {'error': "payment_term is required and must be PREPAID or COLLECT"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from quotes.spot_services import CommodityRateRuleService, RateAvailabilityService
        component_availability = RateAvailabilityService.get_availability(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
        )
        commodity = str(request.data.get('commodity') or 'GCR').upper()
        commodity_coverage = CommodityRateRuleService.evaluate_coverage(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope,
            commodity_code=commodity,
            payment_term=payment_term,
        )

        is_spot, trigger = SpotTriggerEvaluator.evaluate(
            origin_country=origin_country,
            destination_country=destination_country,
            direction=direction,
            service_scope=service_scope,
            component_availability=component_availability,
            commodity_code=commodity,
            commodity_coverage=commodity_coverage,
        )
        
        return Response({
            'is_spot_required': is_spot,
            'trigger': {
                'code': trigger.code,
                'text': trigger.text,
                'missing_components': trigger.missing_components,
                'missing_product_codes': trigger.missing_product_codes,
                'spot_required_product_codes': trigger.spot_required_product_codes,
                'manual_required_product_codes': trigger.manual_required_product_codes,
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
            "payment_term": "PREPAID",
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
        payment_term = str(request.data.get("payment_term") or "").upper()
        if payment_term not in {"PREPAID", "COLLECT"}:
            return Response(
                {"error": "payment_term is required and must be PREPAID or COLLECT"},
                status=400
            )
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
            payment_term=payment_term,
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
        spe_qs = _spe_queryset()
        if not _user_is_manager_or_admin(request.user):
            spe_qs = spe_qs.filter(created_by=request.user)

        # Filter by status if provided
        status_param = request.query_params.get('status')
        if status_param:
            spe_qs = spe_qs.filter(status=status_param)

        spes = spe_qs.order_by('-created_at')[:20]
        
        serializer = SpotPricingEnvelopeSerializer(spes, many=True)
        return Response(serializer.data)
    
    @transaction.atomic
    def post(self, request):
        """Create new SPE in DRAFT status."""
        try:
            data = request.data
            quote = None
            quote_id = data.get('quote_id')
            if quote_id:
                quote = get_quote_for_user(request.user, quote_id)
                from quotes.state_machine import is_quote_editable
                if not is_quote_editable(quote):
                    return Response(
                        {'error': f"Cannot create SPE for locked quote ({quote.status})."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Validate required fields
            required = ['shipment_context', 'trigger_code', 'trigger_text']
            for field in required:
                if field not in data:
                    return Response(
                        {'error': f'Missing required field: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create DB record
            ctx = _normalize_shipment_context(data['shipment_context'])
            if (
                not ctx.get("payment_term")
                and quote is not None
                and getattr(quote, "payment_term", None)
            ):
                ctx["payment_term"] = str(quote.payment_term).upper()
            if "missing_components" not in ctx:
                resolved_missing_components = _resolve_missing_components_for_context(ctx)
                if resolved_missing_components is not None:
                    ctx["missing_components"] = resolved_missing_components
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
                quote=quote,
            )
            
            # Create charge lines (optional)
            charges_data = data.get('charges', [])
            for charge in charges_data:
                rate_val = charge.get('rate') if charge.get('rate') not in ("", None) else None
                min_amount_val = charge.get('min_amount') if charge.get('min_amount') not in ("", None) else None
                max_amount_val = charge.get('max_amount') if charge.get('max_amount') not in ("", None) else None
                percent_val = charge.get('percent') if charge.get('percent') not in ("", None) else None
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
                    min_charge=charge.get('min_charge'),
                    note=charge.get('note') or "",
                    exclude_from_totals=charge.get('exclude_from_totals', False),
                    percentage_basis=charge.get('percentage_basis'),
                    calculation_type=charge.get('calculation_type'),
                    unit_type=charge.get('unit_type'),
                    rate=rate_val,
                    min_amount=min_amount_val,
                    max_amount=max_amount_val,
                    percent=percent_val,
                    percent_basis=charge.get('percent_basis'),
                    rule_meta=charge.get('rule_meta') or {},
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
            
            serializer = SpotPricingEnvelopeSerializer(spe_db)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Unexpected error creating SPE")
            return Response(
                {'error': f"Internal Server Error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    

    
    def _validate_spe(self, spe_db):
        """Validate SPE via Pydantic schemas."""
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        if not ctx.get("payment_term") and getattr(spe_db, "quote", None) and getattr(spe_db.quote, "payment_term", None):
            ctx["payment_term"] = str(spe_db.quote.payment_term).upper()
        resolved_missing_components = _resolve_missing_components_for_context(ctx)
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
                min_charge=float(cl.min_charge) if cl.min_charge is not None else None,
                note=cl.note,
                exclude_from_totals=cl.exclude_from_totals,
                percentage_basis=cl.percentage_basis,
                calculation_type=cl.calculation_type,
                unit_type=cl.unit_type,
                rate=float(cl.rate) if cl.rate is not None else None,
                min_amount=float(cl.min_amount) if cl.min_amount is not None else None,
                max_amount=float(cl.max_amount) if cl.max_amount is not None else None,
                percent=float(cl.percent) if cl.percent is not None else None,
                percent_basis=cl.percent_basis,
                rule_meta=cl.rule_meta or {},
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
                payment_term=(str(ctx.get('payment_term')).lower() if ctx.get('payment_term') else None),
                missing_components=resolved_missing_components,
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
            _spe_queryset(),
        )
        
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)
    
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
            from decimal import Decimal, InvalidOperation

            def _to_decimal(val):
                if val is None or val == "":
                    return None
                try:
                    return Decimal(str(val))
                except (InvalidOperation, ValueError):
                    return None

            # Delete existing
            spe_db.charge_lines.all().delete()
            
            # Create new
            for charge in data['charges']:
                # Sanitize decimal fields
                amount_val = _to_decimal(charge.get('amount'))
                if amount_val is None or amount_val <= 0:
                    logger.warning(
                        "Skipping non-positive SPE charge on PATCH: spe=%s code=%s amount=%s",
                        spe_db.id,
                        charge.get('code'),
                        charge.get('amount'),
                    )
                    continue
                    
                min_charge_val = _to_decimal(charge.get('min_charge'))
                rate_val = _to_decimal(charge.get('rate'))
                min_amount_val = _to_decimal(charge.get('min_amount'))
                max_amount_val = _to_decimal(charge.get('max_amount'))
                percent_val = _to_decimal(charge.get('percent'))

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
                    exclude_from_totals=charge.get('exclude_from_totals', False),
                    percentage_basis=charge.get('percentage_basis'),
                    calculation_type=charge.get('calculation_type'),
                    unit_type=charge.get('unit_type'),
                    rate=rate_val,
                    min_amount=min_amount_val,
                    max_amount=max_amount_val,
                    percent=percent_val,
                    percent_basis=charge.get('percent_basis'),
                    rule_meta=charge.get('rule_meta') or {},
                    source_reference=charge['source_reference'],
                    entered_by=request.user,
                    entered_at=now,
                )
        
        spe_db.save()
        
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)

    def delete(self, request, envelope_id):
        """Delete a DRAFT SPE."""
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot delete SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        spe_db.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpotEnvelopeAcknowledgeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/acknowledge/
    
    Add Sales acknowledgement to SPE.
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
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
        # Check user has manager role
        if not _user_is_manager_or_admin(request.user):
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
        from core.dataclasses import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
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
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response(
                {'error': f'Location not found: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine shipment type
        origin_country, dest_country = _resolve_country_pair(
            ctx.get('origin_country'),
            ctx.get('destination_country'),
            origin_code=ctx.get('origin_code'),
            destination_code=ctx.get('destination_code'),
        )
        shipment_type = _infer_shipment_type(origin_country, dest_country)
        
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
            commodity_code=ctx.get('commodity') or 'GCR',
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

        resolved_output_currency = _resolve_output_currency_for_shipment(
            shipment_type=shipment.shipment_type,
            payment_term=shipment.payment_term,
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        quote_input = QuoteInput(
            customer_id=getattr(spe_db.quote, 'customer_id', None) or uuid.uuid4(),
            contact_id=getattr(spe_db.quote, 'contact_id', None) or uuid.uuid4(),
            shipment=shipment,
            quote_date=date.today(),
            output_currency=resolved_output_currency,
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
        
        from quotes.completeness import evaluate_from_lines

        resolved_scope = quote_data.get('service_scope') or ctx.get('service_scope') or 'D2D'
        coverage = evaluate_from_lines(
            result.lines,
            shipment_type,
            resolved_scope
        )

        return Response({
            'is_complete': coverage.is_complete,
            'has_missing_rates': not coverage.is_complete,
            'missing_components': coverage.missing_required,
            'completeness_notes': coverage.notes,
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def post(self, request):
        text = request.data.get('text', '')
        pdf_file = request.FILES.get('file')
        spe_id = request.data.get('spe_id')
        source_batch_id = request.data.get('source_batch_id')
        source_kind = _normalize_source_kind(request.data.get('source_kind'))
        target_bucket = _normalize_target_bucket(request.data.get('target_bucket'))
        source_type = _normalize_source_type(request.data.get('source_type'), pdf_file=pdf_file)
        manual_assertions = request.data.get('assertions', [])
        use_ai = request.data.get('use_ai', True)
        pdf_warnings = []
        shipment_context = None

        if isinstance(manual_assertions, str):
            try:
                manual_assertions = json.loads(manual_assertions)
            except json.JSONDecodeError:
                manual_assertions = []

        if isinstance(use_ai, str):
            use_ai = use_ai.strip().lower() not in {"false", "0", "no", "off"}

        if spe_id:
            try:
                spe_db = _get_spe_or_404(request.user, spe_id)
                shipment_context = _normalize_shipment_context(spe_db.shipment_context_json)
                if (
                    shipment_context is not None
                    and not shipment_context.get("payment_term")
                    and getattr(spe_db, "quote", None)
                    and getattr(spe_db.quote, "payment_term", None)
                ):
                    shipment_context["payment_term"] = str(spe_db.quote.payment_term).upper()
            except (SpotPricingEnvelopeDB.DoesNotExist, ValueError):
                pass

        if pdf_file:
            from quotes.ai_intake_service import extract_rate_quote_text_from_pdf

            extraction_result = extract_rate_quote_text_from_pdf(pdf_file.read(), context=shipment_context)
            if not extraction_result.success:
                return Response(
                    {'error': extraction_result.error or 'PDF extraction failed'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            text = extraction_result.text or ''
            pdf_warnings = list(extraction_result.warnings or [])
        
        if not text:
            return Response(
                {'error': 'Either "text" or "file" is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
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
            origin_country, destination_country = _resolve_country_pair(
                shipment_context.get('origin_country', ''),
                shipment_context.get('destination_country', ''),
                origin_code=shipment_context.get('origin_code'),
                destination_code=shipment_context.get('destination_code'),
            )
            direction = _infer_shipment_type(origin_country, destination_country)
            
            from quotes.spot_services import RateAvailabilityService
            availability = RateAvailabilityService.get_availability(
                origin_airport=shipment_context.get('origin_code', ''),
                destination_airport=shipment_context.get('destination_code', ''),
                direction=direction,
                service_scope=shipment_context.get('service_scope', 'P2P'),
                payment_term=shipment_context.get('payment_term'),
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
            logger.info(
                "analyze-reply AI result: assertions=%d, warnings=%d, can_proceed=%s",
                len(result.assertions), len(result.warnings), result.summary.can_proceed,
            )
            if not result.assertions:
                logger.warning("analyze-reply returned 0 assertions for text of length %d", len(text))
        else:
            # Manual edit flow or fallback
            result = ReplyAnalysisService.analyze_manual(
                raw_text=text,
                assertions=manual_assertions
            )

        if pdf_warnings:
            result.warnings.extend(pdf_warnings)

        # Auto-populate SPE with AI-extracted charges (draft only)
        if use_ai and not manual_assertions and spe_id and shipment_context:
            try:
                spe_db = _get_spe_or_404(request.user, spe_id)
            except (SpotPricingEnvelopeDB.DoesNotExist, ValueError):
                spe_db = None

            if spe_db and spe_db.status == 'draft':
                from decimal import Decimal, InvalidOperation

                def _to_decimal(val):
                    if val is None or val == "":
                        return None
                    try:
                        return Decimal(str(val))
                    except (InvalidOperation, ValueError):
                        return None

                source_reference = str(
                    request.data.get('source_reference')
                    or (pdf_file.name if pdf_file else "Agent reply (AI)")
                )
                source_label = str(
                    request.data.get('label')
                    or _default_source_label(source_kind, target_bucket)
                )
                batch = _get_or_create_source_batch(
                    spe_db=spe_db,
                    request=request,
                    source_batch_id=source_batch_id,
                    source_kind=source_kind,
                    source_type=source_type,
                    target_bucket=target_bucket,
                    label=source_label,
                    source_reference=source_reference,
                    raw_text=text,
                    file_name=pdf_file.name if pdf_file else "",
                    file_content_type=getattr(pdf_file, "content_type", "") if pdf_file else "",
                    analysis_summary_json={
                        "warnings": list(result.warnings or []),
                        "assertion_count": len(result.assertions or []),
                        "can_proceed": getattr(result.summary, "can_proceed", None),
                    },
                )

                auto_charges = ReplyAnalysisService.build_spe_charges_from_analysis(
                    result,
                    source_reference=source_reference,
                    shipment_context=shipment_context,
                )

                now = timezone.now()
                # Replace only this batch's prior AI-imported lines.
                batch.charge_lines.all().delete()

                if auto_charges:
                    for charge in auto_charges:
                        amount_val = _to_decimal(charge.get("amount"))
                        if amount_val is None or amount_val <= 0:
                            continue

                        min_charge_val = _to_decimal(charge.get("min_charge"))

                        SPEChargeLineDB.objects.create(
                            envelope=spe_db,
                            source_batch=batch,
                            code=charge["code"],
                            description=charge["description"],
                            amount=amount_val,
                            currency=charge["currency"],
                            unit=charge["unit"],
                            bucket=charge["bucket"],
                            is_primary_cost=charge.get("is_primary_cost", False),
                            conditional=charge.get("conditional", False),
                            min_charge=min_charge_val,
                            note=charge.get("note") or "",
                            exclude_from_totals=charge.get("exclude_from_totals", False),
                            percentage_basis=charge.get("percentage_basis"),
                            calculation_type=charge.get("calculation_type"),
                            unit_type=charge.get("unit_type"),
                            rate=_to_decimal(charge.get("rate")),
                            min_amount=_to_decimal(charge.get("min_amount")),
                            max_amount=_to_decimal(charge.get("max_amount")),
                            percent=_to_decimal(charge.get("percent")),
                            percent_basis=charge.get("percent_basis"),
                            rule_meta=charge.get("rule_meta") or {},
                            source_reference=charge["source_reference"],
                            entered_by=request.user,
                            entered_at=now,
                        )

                # Update conditional flag in SPE conditions
                if any(c.get("conditional") for c in auto_charges) or spe_db.charge_lines.filter(conditional=True).exists():
                    conditions = spe_db.conditions_json or {}
                    conditions["conditional_charges_present"] = True
                    spe_db.conditions_json = conditions
                    spe_db.save(update_fields=["conditions_json"])

                result_payload = result.model_dump()
                result_payload["source_batch_id"] = str(batch.id)
                result_payload["source_batch_label"] = batch.label
                return Response(result_payload)
        
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
        from core.dataclasses import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal, ServiceComponent
        from parties.models import Company, Contact
        from uuid import UUID
        from datetime import date
        
        spe_db = _get_spe_or_404(
            request.user, 
            envelope_id,
            _spe_queryset(),
        )
        
        # --- 1. Re-run Computation (Same as ComputeView) ---
        # Note: Ideally this setup logic should be shared, but duplicating for safety now.
        
        try:
            spe = _build_spe_from_db(spe_db)
        except ValueError as e:
            return Response({'error': f'Invalid SPE: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        quote_data = request.data.get('quote_request', {})
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response({'error': f'Location not found: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        origin_country, dest_country = _resolve_country_pair(
            ctx.get('origin_country'),
            ctx.get('destination_country'),
            origin_code=ctx.get('origin_code'),
            destination_code=ctx.get('destination_code'),
        )
        shipment_type = _infer_shipment_type(origin_country, dest_country)
            
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
            commodity_code=ctx.get('commodity') or 'GCR',
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

        resolved_output_currency = _resolve_output_currency_for_shipment(
            shipment_type=shipment.shipment_type,
            payment_term=shipment.payment_term,
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
             req_cust = (
                 request.data.get('customer_id')
                 or quote_data.get('customer_id')
             )
             if req_cust:
                 try:
                     cust_id = UUID(str(req_cust))
                 except (TypeError, ValueError):
                     return Response(
                         {'error': f'Invalid customer_id: {req_cust}'},
                         status=status.HTTP_400_BAD_REQUEST
                     )

        # Backward compatibility for older envelopes without explicit customer_id:
        # resolve by customer_name from shipment context if available.
        if not cust_id:
            customer_name = str(ctx.get('customer_name') or '').strip()
            if customer_name:
                cust = Company.objects.filter(name__iexact=customer_name).first()
                if not cust:
                    cust = Company.objects.filter(name__icontains=customer_name).first()
                if cust:
                    cust_id = cust.id
        
        if not cust_id:
            return Response(
                {'error': 'Customer is required to create quote. Provide customer_id or link SPE to an existing quote.'},
                status=status.HTTP_400_BAD_REQUEST
            )

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
            output_currency=resolved_output_currency,
        )
        
        adapter = PricingServiceV4Adapter(quote_input=quote_input, spot_envelope_id=UUID(str(spe_db.id)))
        
        try:
            result = adapter.calculate_charges()
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from quotes.completeness import evaluate_from_lines
        resolved_scope = quote_data.get('service_scope') or ctx.get('service_scope') or 'D2D'
        coverage = evaluate_from_lines(
            result.lines,
            shipment_type,
            resolved_scope
        )
        if not coverage.is_complete:
            return Response(
                {
                    'error': coverage.notes or 'Missing required components for SPOT coverage.',
                    'has_missing_rates': True,
                    'missing_components': coverage.missing_required,
                    'completeness_notes': coverage.notes,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- 2. Create/Update Quote ---
        if spe_db.quote:
            quote = spe_db.quote
            quote.status = Quote.Status.DRAFT
            quote.output_currency = quote_input.output_currency
            quote.incoterm = shipment.incoterm
            quote.payment_term = shipment.payment_term
            quote.service_scope = shipment.service_scope
            quote.shipment_type = shipment_type
            quote.origin_location = origin_loc
            quote.destination_location = dest_loc
            quote.request_details_json = quote_input.model_dump(mode='json')
            quote.save(update_fields=[
                'status',
                'output_currency',
                'incoterm',
                'payment_term',
                'service_scope',
                'shipment_type',
                'origin_location',
                'destination_location',
                'request_details_json',
            ])
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
                is_informational=getattr(line_data, 'is_informational', False),
                leg=getattr(line_data, 'leg', None),
                bucket=getattr(line_data, 'bucket', None),
                gst_category=getattr(line_data, 'gst_category', None),
                gst_rate=getattr(line_data, 'gst_rate', 0),
                gst_amount=getattr(line_data, 'gst_amount', 0),
                conditional=getattr(line_data, 'conditional', False),
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

