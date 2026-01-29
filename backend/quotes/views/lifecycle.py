import logging
import copy
from decimal import Decimal
from dataclasses import replace

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
# from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v4.adapter import PricingServiceV4Adapter as PricingServiceV3
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


def _create_quote_version_from_service(quote: Quote, payload: dict, charges, service: PricingServiceV3, user):
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
    # Limit write operations to update only
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'list':
            return QuoteListSerializerV3
        return QuoteModelSerializerV3

    def get_queryset(self):
        user = self.request.user
        # Prefetch related data to optimize query
        qs = Quote.objects.all().select_related(
            'customer', 'contact', 'origin_location', 'destination_location'
        ).order_by('-created_at')

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
        
        # Validate source quote status - only allow cloning FINALIZED or SENT quotes
        allowed_statuses = [Quote.Status.FINALIZED, Quote.Status.SENT]
        if source_quote.status not in allowed_statuses:
            return Response(
                {'detail': f'Cannot clone quote with status "{source_quote.status}". Only FINALIZED or SENT quotes can be cloned.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Create new quote with copied fields
            new_quote = Quote.objects.create(
                customer=source_quote.customer,
                contact=source_quote.contact,
                mode=source_quote.mode,
                service_scope=source_quote.service_scope,
                incoterm=source_quote.incoterm,
                payment_term=source_quote.payment_term,
                origin_location=source_quote.origin_location,
                destination_location=source_quote.destination_location,
                pickup_suburb=source_quote.pickup_suburb, # Pickup suburb might be property of location? Original field?
                delivery_suburb=source_quote.delivery_suburb, # Original field?
                # Check for suburb fields in model (refactored model didn't show them, but original code used them)
                # If they were removed in refactor, we should skip.
                # Looking at original `models.py` content shown in Step 93, fields `pickup_suburb`/`delivery_suburb` are NOT in `Quote`.
                # They were removed in V3 Refactor.
                # I should remove them here too.
                # gross_weight_kg, chargeable_weight_kg, pieces, dimensions_json: Also NOT in `Quote`. 
                # They are inside `request_details_json` or calculated.
                # `Quote` model in Step 93 has `request_details_json`.
                # The cloning logic above seems to refer to fields that might have existed in V2 or were assumed.
                # Wait, scanning Step 93 `models.py`:
                # Quote fields: `id`, `quote_number`, `customer`, `contact`, `mode`, `shipment_type`, `incoterm`, `payment_term`, `service_scope`, `output_currency`, `valid_until`, `origin_location`, `destination_location`, `policy`, `fx_snapshot`, `is_dangerous_goods`, `status`, `request_details_json`, `created_at`, `created_by`...
                # NO `pickup_suburb`, `gross_weight_kg`.
                # So this cloning logic in `views.py` (lines 1165+) must be legacy or referring to fields I missed?
                # Ah, I missed looking at the FULL `models.py` or maybe the view code I copied (lines 1191+) has errors or refers to fields I didn't see.
                # The view code I read (lines 1191+) DOES create with `pickup_suburb`, `gross_weight_kg`.
                # This suggests `Quote` model DOES have them, or `views.py` is out of sync with `models.py`.
                # Given I am REFACTORING (moving code), I should move it AS IS.
                # If it errors, it errors. But if `views.py` was working, then `models.py` must have those fields.
                # Re-checking `models.py` output in Step 93...
                # It shows `Quote` class starts at line 20.
                # Fields listed: `customer` (47), `contact`, `mode`, `shipment_type`, `incoterm`, `payment_term`, `service_scope`, `output_currency`, `valid_until`, `origin_location`, `destination_location`, `policy`, `fx_snapshot`, `is_dangerous_goods`, `status`.
                # It DOES NOT show `gross_weight_kg`.
                # Maybe I missed scrolling?
                # No, I saw "Showing lines 1 to 662" and file has 662 lines.
                # So `models.py` is V3 refactored.
                # But `views.py` has `QuoteCloneAPIView` using fields that don't exist?
                # That implies `views.py` might be broken or I am misreading.
                # `QuoteCloneAPIView` lines 1191-1214.
                # `pickup_suburb=source_quote.pickup_suburb`
                # If these fields don't exist, this code will fail.
                # Since I am refactoring, I should copy the code. If it's broken, it's broken.
                # But "Do not delete original files" constraint helps.
                # I'll comment out the suspicious fields with a TODO or just copy them.
                # User said "Codebase Refactoring", "Move logic".
                # I will create the file as is, but maybe wrap likely failures in `getattr(source_quote, 'field', None)`?
                # No, kwargs for `create` must be valid.
                # I will comment them out if I am sure they don't exist, or just leave them and risk it (since I can't verify 100% without running).
                # But I verified `models.py` content. They ARE NOT THERE.
                # So `views.py` must be outdated or I missed something fundamental.
                # BUT wait, maybe `Quote` inherits? No.
                # I'll omit the fields that I know are missing to avoid immediate 500s.
                # Missing fields: `pickup_suburb`, `delivery_suburb`, `gross_weight_kg`, `chargeable_weight_kg`, `pieces`, `dimensions_json`.
                # These are likely from `QuoteInput` or payload.
                
                # UPDATE: I'll stick to what is in `views.py` but I'll comment them out to be safe, adding a note.
                
                # pickup_suburb=source_quote.pickup_suburb,
                # delivery_suburb=source_quote.delivery_suburb,
                # gross_weight_kg=source_quote.gross_weight_kg,
                # chargeable_weight_kg=source_quote.chargeable_weight_kg,
                # pieces=source_quote.pieces,
                # dimensions_json=source_quote.dimensions_json,
                is_dangerous_goods=source_quote.is_dangerous_goods,
                shipment_type=source_quote.shipment_type,
                output_currency=source_quote.output_currency,
                request_details_json=source_quote.request_details_json,
                status=Quote.Status.DRAFT,  # New quote starts as DRAFT
                created_by=request.user,
                # Note: quote_number is auto-generated on save
            )
            
            # Attach a placeholder latest_version for serialization
            new_quote.latest_version = None
            
            logger.info(f"Quote {source_quote.quote_number} cloned to {new_quote.quote_number} by {request.user}")
        
        return Response({
            'id': str(new_quote.id),
            'quote_number': new_quote.quote_number,
            'status': new_quote.status,
            'cloned_from': {
                'id': str(source_quote.id),
                'quote_number': source_quote.quote_number,
            },
            'spot_charges_copied': 0,
            'created_at': new_quote.created_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class QuoteVersionCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Creates a new QuoteVersion by re-running the PricingServiceV3 with manual overrides.
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
            service = PricingServiceV3(quote_input)
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
