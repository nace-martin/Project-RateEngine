import logging
import copy
from decimal import Decimal
from dataclasses import replace
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.decorators import action

from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal, OverrideNote
from quotes.serializers import QuoteModelSerializerV3, QuoteListSerializerV3
from services.models import ServiceComponent
from pricing_v4.adapter import PricingServiceV4Adapter
from core.dataclasses import QuoteInput, ManualOverride

# RBAC permissions
from accounts.permissions import (
    CanFinalizeQuotes,
    CanEditQuotes,
)
from quotes.selectors import get_quote_for_user

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

    for line_charge in charges.lines:
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
        )

    totals = charges.totals
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
    
    # We can import `QuoteComputeV3APIView` inside the function, or move the helpers to a common `utils.py`.
    # For now, let's import the view class locally to access its static/class methods (though they are instance methods).
    # Actually, `_classify_shipment_type` was a standalone function in `views.py`.
    # Let's import it from `calculation`.
    
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
    
    # We need an instance to call _build_quote_input... or make it static.
    # It accesses `self._location_to_ref`.
    # This is a bit messy. Refactoring `_build_quote_input` to a standalone function/service would be better.
    # But sticking to "Refactor = Move files" first:
    compute_view = QuoteComputeV3APIView()
    quote_input = compute_view._build_quote_input(
        validated,
        shipment_type,
        origin_location,
        destination_location,
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
        qs = Quote.objects.all().select_related(
            'customer', 'contact', 'origin_location', 'destination_location'
        ).prefetch_related('spot_envelopes').order_by('-created_at')

        # 1. Role-Based Visibility
        if user.is_authenticated:
            role = getattr(user, 'role', '')
            
            # Global View: Admin & Finance
            is_global = (
                getattr(user, 'is_admin', False) or 
                getattr(user, 'is_finance', False) or 
                role in ('admin', 'finance')
            )
            
            if is_global:
                pass # See all
                
            # Manager View: Restricted by Department
            elif getattr(user, 'is_manager', False) or role == 'manager':
                dept = getattr(user, 'department', None)
                if dept:
                    # See quotes from same department users OR own quotes
                    qs = qs.filter(
                        Q(created_by__department=dept) | 
                        Q(created_by=user)
                    )
                else:
                    # No department assigned -> Fallback to own quotes only?
                    # Or see "unassigned"? Strict interpretation suggests restricted.
                    qs = qs.filter(created_by=user)

            # Sales / Standard View: Own quotes only
            else:
                qs = qs.filter(created_by=user)

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

    def retrieve(self, request, *args, **KWARGS):
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

        totals = getattr(latest_version, 'totals', None)
        lines = list(latest_version.lines.select_related('service_component').all())
        display_currency = (
            getattr(quote, 'output_currency', None)
            or getattr(totals, 'total_sell_fcy_currency', None)
            or 'PGK'
        )

        exchange_rates: dict[str, str] = {}
        sell_lines: list[dict[str, Any]] = []
        for line in lines:
            sc = getattr(line, 'service_component', None)
            component_code = getattr(sc, 'code', None) or 'MANUAL'
            leg = getattr(line, 'leg', None) or getattr(sc, 'leg', None) or 'MAIN'
            sell_currency = line.sell_fcy_currency or display_currency or 'PGK'
            if str(sell_currency).upper() != 'PGK':
                line_gst_amount = (line.sell_fcy_incl_gst - line.sell_fcy).quantize(Decimal('0.01'))
            else:
                line_gst_amount = (line.sell_pgk_incl_gst - line.sell_pgk).quantize(Decimal('0.01'))
            if line.exchange_rate and sell_currency and sell_currency.upper() != 'PGK':
                exchange_rates[f"{sell_currency.upper()}/PGK"] = str(line.exchange_rate)

            sell_lines.append({
                'id': str(line.id),
                'line_type': 'COMPONENT',
                'component': component_code,
                'description': line.cost_source_description or getattr(sc, 'description', '') or 'Charge',
                'leg': leg,
                'cost_pgk': str(line.cost_pgk),
                'sell_pgk': str(line.sell_pgk),
                'sell_pgk_incl_gst': str(line.sell_pgk_incl_gst),
                'gst_amount': str(line_gst_amount),
                'sell_fcy': str(line.sell_fcy),
                'sell_fcy_incl_gst': str(line.sell_fcy_incl_gst),
                'sell_currency': sell_currency,
                'margin_percent': None,
                'exchange_rate': str(line.exchange_rate or Decimal('1')),
                'source': line.cost_source or 'stored_quote',
                'is_rate_missing': bool(line.is_rate_missing),
                'is_informational': bool(getattr(line, 'is_informational', False)),
            })

        notes: list[str] = []
        if totals and totals.notes:
            notes.append(str(totals.notes))
        if totals and totals.has_missing_rates and not notes:
            notes.append("Quote contains missing rates and may be incomplete.")

        payload = {
            'quote_id': str(quote.id),
            'quote_number': quote.quote_number,
            'buy_lines': [],
            'sell_lines': sell_lines,
            'totals': {
                'total_sell_ex_gst': (
                    str(totals.total_sell_fcy if display_currency != 'PGK' else totals.total_sell_pgk)
                    if totals else '0.00'
                ),
                'cost_pgk': str(totals.total_cost_pgk if totals else Decimal('0.00')),
                'sell_pgk': str(totals.total_sell_pgk if totals else Decimal('0.00')),
                'sell_pgk_incl_gst': str(totals.total_sell_pgk_incl_gst if totals else Decimal('0.00')),
                'gst_amount': (
                    str(
                        (totals.total_sell_fcy_incl_gst - totals.total_sell_fcy).quantize(Decimal('0.01'))
                        if str(display_currency).upper() != 'PGK'
                        else (totals.total_sell_pgk_incl_gst - totals.total_sell_pgk).quantize(Decimal('0.01'))
                    )
                    if totals else '0.00'
                ),
                'caf_pgk': '0.00',
                'currency': display_currency,
                'total_sell_fcy': str(totals.total_sell_fcy if totals else Decimal('0.00')),
                'total_sell_fcy_incl_gst': str(totals.total_sell_fcy_incl_gst if totals else Decimal('0.00')),
                'total_quote_amount': (
                    str(totals.total_sell_fcy_incl_gst if str(display_currency).upper() != 'PGK' else totals.total_sell_pgk_incl_gst)
                    if totals else '0.00'
                ),
                'total_sell_fcy_currency': str(totals.total_sell_fcy_currency if totals else display_currency),
            },
            'exchange_rates': exchange_rates,
            'computation_date': latest_version.created_at.isoformat() if latest_version.created_at else timezone.now().isoformat(),
            'routing': None,
            'notes': notes,
        }
        return Response(payload)


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
            'is_archived': quote.is_archived,
            'action': action,
            'transitioned_at': timezone.now().isoformat(),
            'transitioned_by': request.user.username,
        })


class QuoteCloneAPIView(APIView):
    """
    POST: Clone a FINALIZED or SENT quote to create a new DRAFT quote.
    """
    permission_classes = [CanEditQuotes]  # Sales/Manager/Admin can clone
    
    def post(self, request, quote_id):
        # Get source quote
        # SECURITY FIX: Enforce IDOR protection
        source_quote = get_quote_for_user(request.user, quote_id)
        
        # Validate source quote status.
        # Keep in sync with frontend Clone button visibility rules.
        allowed_statuses = [Quote.Status.FINALIZED, Quote.Status.SENT, Quote.Status.EXPIRED]
        if source_quote.status not in allowed_statuses:
            return Response(
                {'detail': f'Cannot clone quote with status "{source_quote.status}". Only FINALIZED, SENT, or EXPIRED quotes can be cloned.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            source_latest_version = source_quote.versions.order_by('-version_number').first()
            clone_payload = copy.deepcopy(
                (source_latest_version.payload_json if source_latest_version else None)
                or source_quote.request_details_json
                or {}
            )

            # Create new draft with currently supported Quote fields only.
            new_quote = Quote.objects.create(
                customer=source_quote.customer,
                contact=source_quote.contact,
                mode=source_quote.mode,
                shipment_type=source_quote.shipment_type,
                service_scope=source_quote.service_scope,
                incoterm=source_quote.incoterm,
                payment_term=source_quote.payment_term,
                output_currency=source_quote.output_currency,
                origin_location=source_quote.origin_location,
                destination_location=source_quote.destination_location,
                is_dangerous_goods=source_quote.is_dangerous_goods,
                # Draft clones must not carry source quote expiry.
                valid_until=None,
                policy=source_quote.policy,
                fx_snapshot=source_quote.fx_snapshot,
                request_details_json=clone_payload,
                status=Quote.Status.DRAFT,  # New quote starts as DRAFT
                created_by=request.user,
                # Note: quote_number is auto-generated on save
            )

            # Seed baseline version so cloned quotes always have editable payload context.
            new_version = QuoteVersion.objects.create(
                quote=new_quote,
                version_number=1,
                payload_json=clone_payload,
                policy=(source_latest_version.policy if source_latest_version else source_quote.policy),
                fx_snapshot=(source_latest_version.fx_snapshot if source_latest_version else source_quote.fx_snapshot),
                status=Quote.Status.DRAFT,
                reason=f"Cloned from {source_quote.quote_number}",
                created_by=request.user,
                engine_version=(source_latest_version.engine_version if source_latest_version else 'V4'),
            )

            spot_charges_copied = 0
            if source_latest_version:
                source_lines = list(source_latest_version.lines.select_related('service_component').all())
                cloned_lines = []
                for line in source_lines:
                    if line.service_component and line.service_component.code.startswith('SPOT'):
                        spot_charges_copied += 1
                    cloned_lines.append(QuoteLine(
                        quote_version=new_version,
                        service_component=line.service_component,
                        cost_pgk=line.cost_pgk,
                        cost_fcy=line.cost_fcy,
                        cost_fcy_currency=line.cost_fcy_currency,
                        sell_pgk=line.sell_pgk,
                        sell_pgk_incl_gst=line.sell_pgk_incl_gst,
                        sell_fcy=line.sell_fcy,
                        sell_fcy_incl_gst=line.sell_fcy_incl_gst,
                        sell_fcy_currency=line.sell_fcy_currency,
                        exchange_rate=line.exchange_rate,
                        leg=line.leg,
                        bucket=line.bucket,
                        cost_source=line.cost_source,
                        cost_source_description=line.cost_source_description,
                        is_rate_missing=line.is_rate_missing,
                        is_informational=line.is_informational,
                        conditional=line.conditional,
                        gst_category=line.gst_category,
                        gst_rate=line.gst_rate,
                        gst_amount=line.gst_amount,
                    ))
                if cloned_lines:
                    QuoteLine.objects.bulk_create(cloned_lines)

                source_totals = getattr(source_latest_version, 'totals', None)
                if source_totals:
                    QuoteTotal.objects.create(
                        quote_version=new_version,
                        total_cost_pgk=source_totals.total_cost_pgk,
                        total_sell_pgk=source_totals.total_sell_pgk,
                        total_sell_pgk_incl_gst=source_totals.total_sell_pgk_incl_gst,
                        total_sell_fcy=source_totals.total_sell_fcy,
                        total_sell_fcy_incl_gst=source_totals.total_sell_fcy_incl_gst,
                        total_sell_fcy_currency=source_totals.total_sell_fcy_currency,
                        has_missing_rates=source_totals.has_missing_rates,
                        notes=source_totals.notes,
                        engine_version=source_totals.engine_version,
                    )
                else:
                    QuoteTotal.objects.create(
                        quote_version=new_version,
                        total_sell_fcy_currency=new_quote.output_currency or 'PGK',
                        notes='Cloned without source totals; baseline totals initialized.',
                    )
            else:
                QuoteTotal.objects.create(
                    quote_version=new_version,
                    total_sell_fcy_currency=new_quote.output_currency or 'PGK',
                    notes='Cloned baseline version from request payload.',
                )

            new_quote.latest_version = new_version
            
            logger.info(f"Quote {source_quote.quote_number} cloned to {new_quote.quote_number} by {request.user}")
        
        return Response({
            'id': str(new_quote.id),
            'quote_number': new_quote.quote_number,
            'status': new_quote.status,
            'cloned_from': {
                'id': str(source_quote.id),
                'quote_number': source_quote.quote_number,
            },
            'spot_charges_copied': spot_charges_copied,
            'created_at': new_quote.created_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class QuoteVersionCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Creates a new QuoteVersion by re-running the PricingServiceV4Adapter with manual overrides.
        """
        quote_id = self.kwargs.get("quote_id")
        # SECURITY FIX: Enforce IDOR protection
        original_quote = get_quote_for_user(request.user, quote_id)
        
        # Block version creation for locked quotes (FINALIZED or SENT)
        from quotes.state_machine import is_quote_editable
        if not is_quote_editable(original_quote):
            return Response(
                {"detail": f"Cannot create new version. Quote is {original_quote.status} and locked for editing."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # 1. Load original payload
        original_payload = original_quote.request_details_json
        if not original_payload:
            return Response({"detail": "Original quote payload is missing."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Rebuild the QuoteInput
        try:
            quote_input, _ = _build_quote_input_from_payload(original_payload)
        except Exception as e:
            return Response({"detail": f"Error building input: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Parse & Merge Manual Overrides
        # Validate incoming data
        serializer = ManualChargeSerializer(data=request.data.get("charges", []), many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Start with existing overrides
        current_overrides = {
            str(o.service_component_id): o for o in (quote_input.overrides or [])
        }

        # Add or update with the new overrides from the request
        for charge in serializer.validated_data:
            new_override = ManualOverride(
                service_component_id=charge["service_component_id"].id,
                cost_fcy=charge["cost_fcy"],
                currency=charge["currency"].upper(),
                unit=charge["unit"],
                min_charge_fcy=charge.get("min_charge_fcy") or Decimal("0.0"),
                valid_until=charge.get("valid_until")
            )
            current_overrides[str(new_override.service_component_id)] = new_override
        
        # Create a new QuoteInput with the updated overrides list
        final_overrides = list(current_overrides.values())
        quote_input = replace(quote_input, overrides=final_overrides)

        # 4. Run the REAL Pricing Engine
        try:
            service = PricingServiceV4Adapter(quote_input)
            charges = service.calculate_charges()
        except Exception as e:
            logger.error(f"Pricing engine failed: {e}", exc_info=True)
            return Response({"detail": f"Pricing Error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5. Save Result as New Version
        new_version = _create_quote_version_from_service(
            quote=original_quote,
            payload=original_payload, # We reuse original payload structure
            charges=charges,
            service=service,
            user=request.user
        )
        
        # Update the payload on the quote itself so next time we have these overrides
        updated_payload = copy.deepcopy(original_payload)
        updated_payload['overrides'] = _serialize_overrides_for_payload(quote_input.overrides)
        original_quote.request_details_json = updated_payload
        original_quote.save(update_fields=['request_details_json'])
        
        original_quote.latest_version = new_version

        # 6. Return Response
        return Response(
            QuoteModelSerializerV3(original_quote, context={'request': request}).data, 
            status=status.HTTP_201_CREATED
        )
