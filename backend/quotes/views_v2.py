from __future__ import annotations
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

    data = request.data
    service_scope = data.get("service_scope")
    if service_scope == "AIRPORT_DOOR":
        service_scope = "A2D"

    quote_context = QuoteContext(
        mode=data.get("mode"),
        direction=data.get("direction"),
        scope=service_scope,
        payment_term=data.get("payment_terms"),
        origin_iata=data.get("origin_airport_code"),
        dest_iata=data.get("destination_airport_code"),
        pieces=[{"weight": data.get("weight")}],
        commodity=data.get("commodity"),
        margins={}, # Not used in this feature
        policy={}, # Not used in this feature
        origin_country_currency="AUD", # This should be looked up based on origin_iata
        destination_country_currency="PGK", # This should be looked up based on dest_iata
    )

    try:
        totals: Totals = compute_quote_v2(quote_context)
        return Response(totals.__dict__, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
