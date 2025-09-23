from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .dataclasses_v2 import QuoteContext # Assuming QuoteContext is defined here
from .pricing_service_v2 import compute_quote_v2
from .api.serializers import TotalsSerializer # Import the serializer

class ComputeQuoteView(APIView):
    def post(self, request, *args, **kwargs):
        # For simplicity, directly creating QuoteContext from request data
        # In a real scenario, you'd validate and parse the request data carefully
        quote_context = QuoteContext(
            origin_iata=request.data.get('origin_iata'),
            dest_iata=request.data.get('dest_iata'),
            service_scope=request.data.get('service_scope'),
            payment_term=request.data.get('payment_term'),
            org_id=request.data.get('org_id'),
            # Add other fields from QuoteContext as needed
        )

        totals = compute_quote_v2(quote_context)
        serializer = TotalsSerializer(totals)
        return Response(serializer.data, status=status.HTTP_200_OK)