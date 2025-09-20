from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from .pricing_v2.dataclasses_v2 import QuoteContext, Piece
from .pricing_v2.pricing_service_v2 import compute_quote_v2

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def compute_v2(request):
    if not getattr(settings, "QUOTER_V2_ENABLED", False):
        return Response({"detail":"v2 disabled"}, status=404)
    d = request.data
    ctx = QuoteContext(
        mode=d.get("mode","AIR"),
        origin_iata=d["origin_iata"],
        dest_iata=d["dest_iata"],
        scope=d["scope"],
        payment_term=d["payment_term"],
        pieces=[Piece(**p) for p in d.get("pieces",[])],
        commodity=d.get("commodity","GCR"),
        incoterm=d.get("incoterm"),
        hints=d.get("hints",{}),
    )
    return Response(compute_quote_v2(ctx))
