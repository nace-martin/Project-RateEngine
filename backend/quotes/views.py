import logging
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from django.db.models import Prefetch
from .models import Quote, QuoteVersion

# Our V3 Service and Dataclasses
from pricing_v2.dataclasses_v3 import V3QuoteRequest, ManualCostOverride, DimensionLine

# Our new V3 Serializers
from .serializers import (
    V3QuoteComputeRequestSerializer,
    V3QuoteComputeResponseSerializer,
    QuoteVersionSerializer,
    QuoteEnvelopeV3Serializer,
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
    V3 ViewSet for listing, retrieving, and creating Quotes.
    """
    queryset = Quote.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated] 

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch(
                'versions',
                queryset=QuoteVersion.objects.order_by('-version_number'),
                to_attr='latest_version_list'
            )
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return QuoteEnvelopeV3Serializer
        return V3QuoteComputeResponseSerializer

    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        """
        Returns all versions for a given quote, newest first.
        """
        quote = self.get_object()
        versions = quote.versions.all().order_by('-version_number')
        serializer = QuoteVersionSerializer(versions, many=True)
        return Response(serializer.data)