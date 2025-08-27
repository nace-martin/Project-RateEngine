import decimal
import math
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView  # <<< CORRECTED: APIView is now imported
from .models import Client, RateCard, Quote, ShipmentPiece
from .serializers import ClientSerializer, RateCardSerializer, QuoteSerializer


# --- 2. All ViewSets and Views ---

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

class RateCardViewSet(viewsets.ModelViewSet):
    queryset = RateCard.objects.all()
    serializer_class = RateCardSerializer

# Replace the existing QuoteViewSet in backend/quotes/views.py

class QuoteViewSet(viewsets.ModelViewSet):
    queryset = Quote.objects.all()
    serializer_class = QuoteSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        pieces_data = data.pop('pieces', []) 

        if not pieces_data:
            return Response({"error": "A quote must have at least one shipment piece."}, status=status.HTTP_400_BAD_REQUEST)

        # --- 1. Calculate Totals using the Correct Formula ---
        total_actual_weight = decimal.Decimal(0)
        total_volumetric_weight = decimal.Decimal(0)
        total_volume_cbm = decimal.Decimal(0)

        for piece in pieces_data:
            quantity = int(piece.get('quantity', 1))
            l = decimal.Decimal(piece.get('length_cm', 0))
            w = decimal.Decimal(piece.get('width_cm', 0))
            h = decimal.Decimal(piece.get('height_cm', 0))
            weight = decimal.Decimal(piece.get('weight_kg', 0))

            total_actual_weight += quantity * weight
            
            # CORRECTED FORMULA: Use the / 6000 divisor for precision
            piece_volumetric_weight = (l * w * h) / 6000
            print(f"Piece: L={l}, W={w}, H={h}, Volume={l * w * h}, Volumetric Weight={piece_volumetric_weight}")
            total_volumetric_weight += piece_volumetric_weight * quantity
            
            # Also calculate CBM for storing in the database
            total_volume_cbm += (l * w * h) / 1000000 * quantity


        # --- 2. Round UP and Determine Chargeable Weight ---
        rounded_actual_weight = math.ceil(total_actual_weight)
        rounded_volumetric_weight = math.ceil(total_volumetric_weight)
        
        print(f"Total Actual Weight: {total_actual_weight}")
        print(f"Total Volumetric Weight: {total_volumetric_weight}")
        print(f"Rounded Actual Weight: {rounded_actual_weight}")
        print(f"Rounded Volumetric Weight: {rounded_volumetric_weight}")
        
        chargeable_weight = max(rounded_actual_weight, rounded_volumetric_weight)
        print(f"Chargeable Weight: {chargeable_weight}")

        # --- 3. Find Rate Card and Select Rate ---
        try:
            rate_card = RateCard.objects.get(origin=data.get('origin'), destination=data.get('destination'))
        except RateCard.DoesNotExist:
            return Response({"error": "No rate card found for this route."}, status=status.HTTP_400_BAD_REQUEST)

        rate_per_kg = decimal.Decimal(0)
        # Use the final chargeable_weight to find the correct rate break
        if chargeable_weight > 1000: rate_per_kg = rate_card.brk_1000
        elif chargeable_weight > 500: rate_per_kg = rate_card.brk_500
        elif chargeable_weight > 250: rate_per_kg = rate_card.brk_250
        elif chargeable_weight > 100: rate_per_kg = rate_card.brk_100
        else: rate_per_kg = rate_card.brk_45
        
        # --- 4. Calculate Final Costs ---
        base_cost = max(decimal.Decimal(chargeable_weight) * rate_per_kg, rate_card.min_charge)
        margin_pct = decimal.Decimal(data.get('margin_pct', 20.0)) / 100
        total_sell = base_cost * (1 + margin_pct)

        # --- 5. Save the Quote and its Pieces ---
        final_quote_data = {
            **data,
            'actual_weight_kg': total_actual_weight.quantize(decimal.Decimal('0.01')),
            'volume_cbm': total_volume_cbm.quantize(decimal.Decimal('0.001')),
            'chargeable_weight_kg': chargeable_weight,
            'rate_used_per_kg': rate_per_kg.quantize(decimal.Decimal('0.01')),
            'base_cost': base_cost.quantize(decimal.Decimal('0.01')),
            'total_sell': total_sell.quantize(decimal.Decimal('0.01')),
        }
        
        quote_serializer = self.get_serializer(data=final_quote_data)
        quote_serializer.is_valid(raise_exception=True)
        quote = quote_serializer.save()

        for piece in pieces_data:
            ShipmentPiece.objects.create(
                quote=quote,
                quantity=piece.get('quantity', 1),
                length_cm=piece.get('length_cm', 0),
                width_cm=piece.get('width_cm', 0),
                height_cm=piece.get('height_cm', 0),
                weight_kg=piece.get('weight_kg', 0)
            )
        
        headers = self.get_success_headers(quote_serializer.data)
        return Response(quote_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        
class RouteListView(APIView):
    """
    A view to provide a list of unique origins and destinations.
    """
    def get(self, request, format=None):
        origins = RateCard.objects.values_list('origin', flat=True).distinct()
        destinations = RateCard.objects.values_list('destination', flat=True).distinct()
        data = {
            'origins': list(origins),
            'destinations': list(destinations)
        }
        return Response(data)