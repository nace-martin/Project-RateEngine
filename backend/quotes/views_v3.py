# In: backend/quotes/views_v3.py

import logging
from decimal import Decimal
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# Our V3 Service and Dataclasses
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import V3QuoteRequest, ManualCostOverride

# Our new V3 Serializers
from .serializers_v3 import (
    V3QuoteComputeRequestSerializer,
    V3QuoteComputeResponseSerializer
)

_logger = logging.getLogger(__name__)

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
            # Map manual overrides first
            override_data = data.get('overrides', [])
            manual_overrides = [
                ManualCostOverride(
                    service_component_id=ov['service_component_id'],
                    cost_fcy=ov['cost_fcy'],
                    currency=ov['currency'],
                    unit=ov['unit'],
                    min_charge_fcy=ov.get('min_charge_fcy')
                ) for ov in override_data
            ]

            # Create the main request dataclass
            request_data = V3QuoteRequest(
                customer_id=data['customer_id'],
                contact_id=data['contact_id'],
                mode=data['mode'],
                shipment_type=data['shipment_type'],
                incoterm=data['incoterm'],
                origin_airport_code=data['origin_airport_code'],
                destination_airport_code=data['destination_airport_code'],
                pieces=data['pieces'],
                gross_weight_kg=data['gross_weight_kg'],
                volume_cbm=data['volume_cbm'],
                payment_term=data.get('payment_term', 'PREPAID'),
                output_currency=data.get('output_currency'),
                is_dangerous_goods=data.get('is_dangerous_goods', False),
                overrides=manual_overrides
            )

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
