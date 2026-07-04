import logging
from datetime import date
from decimal import Decimal
from dataclasses import replace
from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.decorators import action

from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from quotes.serializers import (
    CanonicalQuoteResultSerializer,
    QuoteListSerializerV3,
    QuoteModelSerializerV3,
)
from quotes.quote_result_contract import (
    build_persisted_line_item_metadata,
    build_persisted_quote_total_metadata,
    build_quote_result_from_quote,
)
from quotes.services.rate_resolution import (
    RateResolutionContext,
    resolve_quote_rate_dimensions,
)
from services.models import ServiceComponent
from pricing_v4.adapter import PricingServiceV4Adapter
from core.dataclasses import ManualOverride

# RBAC permissions
from accounts.permissions import (
    CanFinalizeQuotes,
    CanEditQuotes,
)
from quotes.selectors import get_quote_for_user, get_quotes_for_user

logger = logging.getLogger(__name__)


class QuoteLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class ManualChargeSerializer(serializers.Serializer):
    service_component_id = serializers.PrimaryKeyRelatedField(queryset=ServiceComponent.objects.all())
    cost_fcy = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    unit = serializers.CharField(max_length=20)
    min_charge_fcy = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)


def _serialize_overrides_for_payload(overrides):
    serialized = []
    for override in overrides or []:
        serialized.append({
            'service_component_id': str(override.service_component_id),
            'cost_fcy': str(override.cost_fcy),
            'currency': override.currency,
            'unit': override.unit,
            'min_charge_fcy': str(override.min_charge_fcy) if override.min_charge_fcy is not None else None,
            'valid_until': override.valid_until,
        })
    return serialized


def _create_quote_version_from_service(quote: Quote, payload: dict, charges, service: PricingServiceV4Adapter, user):
    latest_version = quote.versions.order_by('-version_number').first()
    version_number = 1
    if latest_version:
        version_number = latest_version.version_number + 1

    version = QuoteVersion.objects.create(
        quote=quote,
        version_number=version_number,
        payload_json=payload,
        policy=service.get_policy(),
        fx_snapshot=service.get_fx_snapshot(),
        status=Quote.Status.DRAFT,
        reason="Manual recalculation",
        created_by=user,
        engine_version='V4',  # Always V4 - V3 is deprecated
    )

    component_map = {
        component.id: component
        for component in ServiceComponent.objects.filter(
            id__in=[line.service_component_id for line in charges.lines if getattr(line, "service_component_id", None)]
        ).select_related("service_code")
    }

    for line_charge in charges.lines:
        service_component = component_map.get(line_charge.service_component_id)
        canonical_metadata = build_persisted_line_item_metadata(
            raw_cost_source=line_charge.cost_source,
            service_component=service_component,
            engine_version="V4",
            product_code=getattr(line_charge, "product_code", None) or getattr(line_charge, "service_component_code", None),
            component=getattr(line_charge, "component", None),
            basis=getattr(line_charge, "basis", None),
            rule_family=getattr(line_charge, "rule_family", None),
            service_family=getattr(line_charge, "service_family", None),
            unit_type=getattr(line_charge, "unit_type", None),
            quantity=getattr(line_charge, "quantity", None),
            rate=getattr(line_charge, "rate", None),
            sell_amount=line_charge.sell_fcy if (line_charge.sell_fcy_currency or "PGK").upper() != "PGK" else line_charge.sell_pgk,
            is_rate_missing=bool(line_charge.is_rate_missing),
            leg=line_charge.leg,
            calculation_notes=getattr(line_charge, "calculation_notes", None),
            stored_is_spot_sourced=getattr(line_charge, "is_spot_sourced", None),
            stored_is_manual_override=getattr(line_charge, "is_manual_override", None),
            canonical_cost_source=getattr(line_charge, "canonical_cost_source", None),
            rate_source=getattr(line_charge, "rate_source", None),
        )
        QuoteLine.objects.create(
            quote_version=version,
            service_component_id=line_charge.service_component_id,
            cost_pgk=line_charge.cost_pgk,
            cost_fcy=line_charge.cost_fcy,
            cost_fcy_currency=line_charge.cost_fcy_currency,
            sell_pgk=line_charge.sell_pgk,
            sell_pgk_incl_gst=line_charge.sell_pgk_incl_gst,
            sell_fcy=line_charge.sell_fcy,
            sell_fcy_incl_gst=line_charge.sell_fcy_incl_gst,
            sell_fcy_currency=line_charge.sell_fcy_currency,
            exchange_rate=line_charge.exchange_rate,
            cost_source=line_charge.cost_source,
            cost_source_description=line_charge.cost_source_description,
            is_rate_missing=line_charge.is_rate_missing,
            leg=line_charge.leg,
            bucket=line_charge.bucket,
            gst_category=line_charge.gst_category,
            gst_rate=line_charge.gst_rate,
            gst_amount=line_charge.gst_amount,
            product_code=canonical_metadata["product_code"] or None,
            component=canonical_metadata["component"],
            basis=canonical_metadata["basis"],
            rule_family=canonical_metadata["rule_family"],
            service_family=canonical_metadata["service_family"],
            unit_type=canonical_metadata["unit_type"],
            rate=canonical_metadata["rate"],
            rate_source=canonical_metadata["rate_source"],
            canonical_cost_source=canonical_metadata["canonical_cost_source"],
            is_spot_sourced=canonical_metadata["is_spot_sourced"],
            is_manual_override=canonical_metadata["is_manual_override"],
            calculation_notes=canonical_metadata["calculation_notes"],
        )

    totals = charges.totals
    total_metadata = build_persisted_quote_total_metadata(totals)
    QuoteTotal.objects.create(
        quote_version=version,
        total_cost_pgk=totals.total_cost_pgk,
        total_sell_pgk=totals.total_sell_pgk,
        total_sell_pgk_incl_gst=totals.total_sell_pgk_incl_gst,
        total_sell_fcy=totals.total_sell_fcy,
        total_sell_fcy_incl_gst=totals.total_sell_fcy_incl_gst,
        total_sell_fcy_currency=totals.total_sell_fcy_currency,
        has_missing_rates=totals.has_missing_rates,
        notes=totals.notes,
        engine_version='V4',  # Always V4 - V3 is deprecated
        service_notes=total_metadata["service_notes"],
        customer_notes=total_metadata["customer_notes"],
        internal_notes=total_metadata["internal_notes"],
        warnings_json=total_metadata["warnings_json"],
        audit_metadata_json=total_metadata["audit_metadata_json"],
    )

    quote.request_details_json = payload
    quote.latest_version = version
    quote.output_currency = service.get_output_currency()
    quote.save(update_fields=['request_details_json', 'output_currency'])

    return version


def _build_quote_input_from_payload(payload: dict):
    # This function requires importing View helper or duplicating logic.
    # To avoid circular imports, let's look at what it does:
    # 1. Validates payload via Pydantic
    # 2. Gets Locations
    # 3. Classifies Shipment Type (requires helper)
    # 4. Builds QuoteInput (requires helper)
    
    # We can import QuoteComputeV3APIView inside the function, or move the helpers to a common `utils.py`.
    # For now, let's import the view class locally to access its static/class methods (though they are instance methods).
    # Actually, _classify_shipment_type was a standalone function in `views.py`.
    # Let's import it from calculation.
    from .calculation import _classify_shipment_type, QuoteComputeV3APIView
    from quotes.schemas import QuoteComputeRequest
    from core.models import Location
    from pydantic import ValidationError

    try:
        validated = QuoteComputeRequest(**payload)
    except ValidationError as e:
        raise ValueError(f"Invalid payload: {e}")

    origin_location = get_object_or_404(Location, pk=validated.origin_location_id, is_active=True)
    destination_location = get_object_or_404(Location, pk=validated.destination_location_id, is_active=True)
    shipment_type = _classify_shipment_type(
        validated.mode,
        origin_location,
        destination_location,
    )
    resolved_dimensions = resolve_quote_rate_dimensions(
        RateResolutionContext(
            customer_id=validated.customer_id,
            shipment_type=shipment_type,
            service_scope=validated.service_scope,
            payment_term=validated.payment_term,
            origin_airport=origin_location.code,
            destination_airport=destination_location.code,
            quote_date=date.today(),
            override_buy_currency=validated.buy_currency,
            override_agent_id=validated.agent_id,
            override_carrier_id=validated.carrier_id,
        )
    )
    
    # We need an instance to call _build_quote_input... or make it static.
    # It accesses `self._location_to_ref`.
    # This is a bit messy. Refactoring _build_quote_input to a standalone function/service would be better.
    # But sticking to "Refactor = Move files" first:
    compute_view = QuoteComputeV3APIView()
    quote_input = compute_view._build_quote_input(
        validated,
        shipment_type,
        origin_location,
        destination_location,
        resolved_dimensions,
    )
    return quote_input, validated


class QuoteV3ViewSet(viewsets.ModelViewSet):
    """
    Provides CRUD endpoints for V3 Quotes.
    Note: Most updates are done via specialized endpoints (compute, transition).
    PATCH supports status updates for auto-rated quote finalization.
    """
    queryset = Quote.objects.all().order_by('-created_at')
    serializer_class = QuoteModelSerializerV3
    permission_classes = [IsAuthenticated]
    pagination_class = QuoteLimitOffsetPagination
    # Limit write operations to update and delete only
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'list':
            return QuoteListSerializerV3
        return QuoteModelSerializerV3

    def get_queryset(self):
        user = self.request.user
        # Prefetch related data to optimize query
        base_qs = Quote.objects.all().select_related(
            'customer', 'contact', 'origin_location', 'destination_location'
        ).prefetch_related('spot_envelopes').order_by('-created_at')

        # 1. Role-Based Visibility & IDOR Protection
        qs = get_quotes_for_user(user, base_qs)

        # 2. Filtering (Manual implementation since django-filter is not installed)
        mode = self.request.query_params.get('mode')
        if mode:
            qs = qs.filter(mode=mode.upper())

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
            
        # Filter by creator (Manager/Admin only)
        creator_id = self.request.query_params.get('created_by')
        if creator_id:
            # Ideally verify permission again, but filtering by any creator is harmless 
            # if the base queryset is already restricted for Sales.
            qs = qs.filter(created_by_id=creator_id)

        opportunity_id = self.request.query_params.get('opportunity')
        if opportunity_id:
            qs = qs.filter(opportunity_id=opportunity_id)

        # 3. Archival Filtering
        is_archived_param = self.request.query_params.get('is_archived')        
        if is_archived_param is not None:
            is_archived = is_archived_param.lower() in ['true', '1', 'yes']
            qs = qs.filter(is_archived=is_archived)

        if self.action == 'list':
            # List view only needs totals for the latest version
            return qs.prefetch_related('versions__totals')
        
        # Detail view needs lines for the latest version
        return qs.prefetch_related(
            'versions__lines__service_component',
            'versions__totals'
        )

    def get_object(self):
        """
        Override to ensure object-level access control using secure selector
        """
        # Use the secure selector that enforces RBAC
        quote_id = self.kwargs[self.lookup_field]
        return get_quote_for_user(self.request.user, quote_id, self.filter_queryset(self.get_queryset()))

    def destroy(self, request, *args, **kwargs):
        """
        Delete a quote. Only allowed if the quote implies DRAFT status.
        """
        instance = self.get_object()
        if instance.status != Quote.Status.DRAFT:
            return Response(
                {'detail': f'Cannot delete quote with status "{instance.status}". Only DRAFT quotes can be deleted.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def retrieve(self, request, *args, **kwargs):
        """
        Custom retrieve to ensure we always fetch the 'latest_version'.
        """
        instance = self.get_object()
        # Find the latest version
        latest_version = instance.versions.order_by('-version_number').first()
        instance.latest_version = latest_version
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """
        Custom list to add 'latest_version' to each quote using prefetched data.
        """
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            for quote in page:
                # Use prefetched cache to avoid DB hit
                versions = list(quote.versions.all())
                # QuoteVersion has ordering = ['quote', '-version_number'] so we can just grab first
                quote.latest_version = versions[0] if versions else None
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        for quote in queryset:
             versions = list(quote.versions.all())
             quote.latest_version = versions[0] if versions else None

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH endpoint - only allows updating specific fields.
        Used for auto-rated quote finalization (INCOMPLETE → DRAFT).
        """
        instance = self.get_object()
        
        # Only allow status updates
        allowed_fields = {'status'}
        update_fields = set(request.data.keys())
        
        if not update_fields.issubset(allowed_fields):
            disallowed = update_fields - allowed_fields
            return Response(
                {'detail': f'Cannot update fields: {", ".join(disallowed)}. Only status can be updated via PATCH.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate status transition
        new_status = request.data.get('status')
        if new_status:
            # For INCOMPLETE quotes, allow transition to DRAFT
            if instance.status == Quote.Status.INCOMPLETE and new_status == 'DRAFT':
                instance.status = Quote.Status.DRAFT
                instance.save(update_fields=['status'])
                
                # Re-fetch with latest version
                latest_version = instance.versions.order_by('-version_number').first()
                instance.latest_version = latest_version
                serializer = self.get_serializer(instance)
                return Response(serializer.data)
            else:
                return Response(
                    {'detail': f'Invalid status transition from {instance.status} to {new_status}. Use /transition/ endpoint for other transitions.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

    @action(detail=True, methods=['get'], url_path='compute_v3')
    def compute_v3(self, request, *args, **kwargs):
        """
        Compatibility endpoint for legacy frontend quote compute fetches.

        Returns a QuoteComputeResult-shaped payload synthesized from the stored
        latest quote version (which is now produced by the V4 engine).
        """
        quote = self.get_object()

        latest_version = quote.versions.order_by('-version_number').first()
        if not latest_version:
            return Response(
                {'detail': 'Quote has no computed version data.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = build_quote_result_from_quote(quote, latest_version)
        serializer = CanonicalQuoteResultSerializer(result)
        return Response(serializer.data)


class QuoteTransitionAPIView(APIView):
    """
    POST: Transition quote status (finalize, send).
    """
    permission_classes = [CanFinalizeQuotes]  # Sales/Manager/Admin can finalize; Finance excluded
    
    def get(self, request, quote_id):
        """Get current status and available transitions."""
        from quotes.state_machine import QuoteStateMachine, get_status_display_info
        
        # SECURITY FIX: Enforce IDOR protection
        quote = get_quote_for_user(request.user, quote_id)
        machine = QuoteStateMachine(quote)
        
        return Response({
            'quote_id': str(quote.id),
            'current_status': quote.status,
            'status_info': get_status_display_info(quote.status),
            'available_transitions': machine.available_transitions,
            'is_editable': machine.is_editable,
            'finalized_at': quote.finalized_at.isoformat() if quote.finalized_at else None,
            'finalized_by': quote.finalized_by.username if quote.finalized_by else None,
            'sent_at': quote.sent_at.isoformat() if quote.sent_at else None,
            'sent_by': quote.sent_by.username if quote.sent_by else None,
        })
    
    def post(self, request, quote_id):
        """Perform status transition."""
        from quotes.state_machine import QuoteStateMachine
        
        # SECURITY FIX: Enforce IDOR protection
        quote = get_quote_for_user(request.user, quote_id)
        machine = QuoteStateMachine(quote)
        
        action = request.data.get('action', '').lower()
        
        if action == 'finalize':
            from quotes.spot_views import _spot_exception_blockers

            spot_blockers = []
            for spe in quote.spot_envelopes.prefetch_related("charge_lines").all():
                spot_blockers.extend(_spot_exception_blockers(spe))
            if spot_blockers:
                return Response(
                    {
                        'detail': 'Cannot finalize quote with unresolved SPOT charge review lines.',
                        'blocking_issues': spot_blockers,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check for missing rates before finalizing
            latest_version = quote.versions.order_by('-version_number').first()
            if latest_version:
                totals = getattr(latest_version, 'totals', None)
                if totals and totals.has_missing_rates:
                    return Response(
                        {'detail': 'Cannot finalize quote with missing rates. Complete all required rates first.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            success, error = machine.finalize(user=request.user)
            
        elif action == 'send':
            success, error = machine.mark_sent(user=request.user)
        
        elif action == 'cancel':
            # Cancel a draft quote (permanent delete)
            success, error = machine.cancel(user=request.user)
            
        elif action == 'mark_won':
            # Mark as accepted/won
            success, error = machine.mark_won(user=request.user)
            
        elif action == 'mark_lost':
            # Mark as lost
            success, error = machine.mark_lost(user=request.user)
            
        elif action == 'mark_expired':
            # Mark as expired
            success, error = machine.mark_expired(user=request.user)
            
        else:
            return Response(
                {'detail': f'Invalid action "{action}". Valid actions: finalize, send, cancel, mark_won, mark_lost, mark_expired.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not success:
            return Response(
                {'detail': error},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action == 'cancel':
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Return updated quote
        quote.refresh_from_db()
        return Response({
            'quote_id': str(quote.id),
            'status': quote.status,
            'status_display': quote.get_status_display(),
        })


class QuoteCloneAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        from .services import clone_quote
        # SECURITY FIX: Enforce IDOR protection
        original_quote = get_quote_for_user(request.user, quote_id)
        
        cloned_quote = clone_quote(original_quote, request.user)
        serializer = QuoteModelSerializerV3(cloned_quote, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class QuoteVersionCreateAPIView(APIView):
    permission_classes = [CanEditQuotes]

    def post(self, request, quote_id):
        from .services import create_quote_version
        # SECURITY FIX: Enforce IDOR protection
        quote = get_quote_for_user(request.user, quote_id)
        
        try:
            version = create_quote_version(quote, request.data, request.user)
            serializer = QuoteModelSerializerV3(version.quote, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            # SECURITY FIX: Don't expose internal exception details to users
            return Response({'error': 'An error occurred processing your request'}, status=status.HTTP_400_BAD_REQUEST)