from django.conf import settings
from pricing_v2.dataclasses_v2 import QuoteContext, Totals
from pricing_v2.pricing_service_v2 import compute_quote_v2
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["POST"])
def compute_quote_v2_api(request):
    if not settings.QUOTER_V2_ENABLED:
        return Response(
            {"detail": "Quoter V2 is not enabled."}, status=status.HTTP_404_NOT_FOUND
        )

    # In a real scenario, you would validate and deserialize the request data
    # into a QuoteContext object. For now, we'll create a dummy one.
    quote_context = QuoteContext()  # Replace with actual deserialization

    try:
        totals: Totals = compute_quote_v2(quote_context)
        # In a real scenario, you would serialize the Totals object to JSON
        return Response(totals.__dict__, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
