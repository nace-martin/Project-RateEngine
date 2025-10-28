# In: backend/quotes/views_v3.py

import logging
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Quote

# Our V3 Service and Dataclasses
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import V3QuoteRequest, ManualCostOverride, DimensionLine

# Our new V3 Serializers
from .serializers_v3 import (
    V3QuoteComputeRequestSerializer,
    V3QuoteComputeResponseSerializer,
    QuoteVersionSerializer,
)

_logger = logging.getLogger(__name__)


def _build_quote_request_from_validated_data(data: dict) -> V3QuoteRequest:
    """
    Construct the V3QuoteRequest dataclass from validated serializer data.
    Shared between the viewset and the standalone compute view.
    """
    override_data = data.get('overrides', [])
    manual_overrides = [
        ManualCostOverride(
            service_component_id=ov['service_component_id'],
            cost_fcy=ov['cost_fcy'],
            currency=ov['currency'],
            unit=ov['unit'],
            min_charge_fcy=ov.get('min_charge_fcy'),
        )
        for ov in override_data
    ]

    dimension_data = data.get('dimensions', [])
    dimension_lines = [
        DimensionLine(
            pieces=line['pieces'],
            length_cm=line['length_cm'],
            width_cm=line['width_cm'],
            height_cm=line['height_cm'],
            gross_weight_kg=line['gross_weight_kg'],
        )
        for line in dimension_data
    ]

    return V3QuoteRequest(
        customer_id=data['customer_id'],
        contact_id=data['contact_id'],
        mode=data['mode'],
        shipment_type=data['shipment_type'],
        incoterm=data['incoterm'],
        origin_airport_code=data['origin_airport_code'],
        destination_airport_code=data['destination_airport_code'],
        dimensions=dimension_lines,
        payment_term=data.get('payment_term', 'PREPAID'),
        output_currency=data.get('output_currency'),
        is_dangerous_goods=data.get('is_dangerous_goods', False),
        overrides=manual_overrides,
    )


class QuoteV3ViewSet(viewsets.ModelViewSet):
    """
    ViewSet exposing list, retrieve, and create operations for V3 quotes.
    Creation delegates to the PricingServiceV3.
    """

    queryset = Quote.objects.all().prefetch_related(
        'versions__lines__service_component',
        'versions__totals',
    ).order_by('-created_at')
    serializer_class = V3QuoteComputeResponseSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        quote = self.get_object()
        serializer = self.get_serializer(quote)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        request_serializer = V3QuoteComputeRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            request_data = _build_quote_request_from_validated_data(request_serializer.validated_data)
            _logger.info("Calling PricingServiceV3.compute_v3 via QuoteV3ViewSet...")
            service = PricingServiceV3()
            new_quote = service.compute_v3(request_data)
        except Exception as exc:
            _logger.exception("Error during V3 quote computation via viewset: %s", exc)
            return Response(
                {"detail": f"An error occurred: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = self.get_serializer(new_quote)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        """
        Returns all versions for a given quote, newest first.
        """
        quote = self.get_object()
        versions = quote.versions.all().order_by('-version_number')
        serializer = QuoteVersionSerializer(versions, many=True)
        return Response(serializer.data)


class QuoteComputeV3APIView(generics.CreateAPIView):
    """
    Main V3 API Endpoint for computing and saving a new quote.
    """
    serializer_class = V3QuoteComputeRequestSerializer
    permission_classes = [IsAuthenticated] # Protect this endpoint

    def create(self, request, *args, **kwargs):
        # 1. Validate the incoming request payload
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # 2. Map validated data to our V3QuoteRequest dataclass
        try:
            # Create the main request dataclass
            request_data = _build_quote_request_from_validated_data(data)

            # 3. Call the Pricing Service!
            _logger.info("Calling PricingServiceV3.compute_v3...")
            service = PricingServiceV3()
            # We pass the authenticated user to the service (if service uses it)
            # We'll need to update the service to accept this
            
            # TODO: Update compute_v3 to accept 'user' for created_by fields
            # new_quote = service.compute_v3(request_data, user=request.user)
            
            # For now, we call it as-is
            new_quote = service.compute_v3(request_data)
            _logger.info(f"Successfully computed and saved Quote {new_quote.quote_number}")

            # 4. Serialize the response
            response_serializer = V3QuoteComputeResponseSerializer(new_quote)
            
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            _logger.exception(f"Error during V3 quote computation: {e}")
            return Response(
                {"detail": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class QuoteRetrieveV3APIView(generics.RetrieveAPIView):
    """
    API view to retrieve a single V3 Quote by its UUID.
    GET /api/v3/quotes/{id}/
    """
    queryset = Quote.objects.all().prefetch_related(
        'versions__lines__service_component',
        'versions__totals'
    )
    serializer_class = V3QuoteComputeResponseSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_object(self):
        """
        Retrieve the quote ensuring we get the latest version ordered correctly.
        Override is needed because the default manager might not apply
        the ordering defined in the QuoteVersion Meta.
        """
        queryset = self.get_queryset().order_by('-versions__version_number')

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.kwargs, (
            'Expected view %s to be called with a URL keyword argument named "%s". '
            'Fix your URL conf, or set the `.lookup_field` attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        obj = get_object_or_404(queryset, **filter_kwargs)

        self.check_object_permissions(self.request, obj)

        return obj
