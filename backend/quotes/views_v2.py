from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from ..pricing_v2.pricing_service_v2 import build_buy_menu, select_best_offer
from ..pricing_v2.dataclasses_v2 import QuoteContext, PaymentTerm
from datetime import datetime

from .serializers_v2 import QuoteResponseSerializerSales, QuoteResponseSerializerManager

class ComputeV2(APIView):
    def get_serializer_class(self):
        if self.request.user.groups.filter(name='Sales').exists():
            return QuoteResponseSerializerSales
        return QuoteResponseSerializerManager

    def post(self, request, *args, **kwargs):
        # A real implementation would involve deserializing the request data
        # into a serializer and building the QuoteContext from it.
        # Here we create a dummy context for demonstration.
        context = QuoteContext(
            shipment_pieces=request.data.get("shipment_pieces", []),
            audience=request.data.get("audience", ""),
            payment_term=PaymentTerm(request.data.get("payment_term", "PREPAID")),
            compute_at=datetime.now(),
            origin=request.data.get("origin", ""),
            destination=request.data.get("destination", ""),
            spot_offers=request.data.get("spot_offers", [])
        )

        buy_menu = build_buy_menu(context)

        if not buy_menu.offers:
            serializer = self.get_serializer_class()({"is_incomplete": True, "reason": "No BUY offers found."})
            return Response(serializer.data, status=status.HTTP_200_OK)

        best_offer = select_best_offer(context, buy_menu)

        # Placeholder for snapshot generation
        snapshot = {
            "selection_rationale": "Placeholder: No selection rationale implemented yet.",
            "included_fees": [],
            "skipped_fees_with_reasons": [],
            "phase_timings_ms": {},
        }

        response_data = {
            "best_buy_offer": best_offer,
            "snapshot": snapshot
        }

        serializer = self.get_serializer_class()(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
