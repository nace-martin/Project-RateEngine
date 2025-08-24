from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Client, RateCard, Quote
from .serializers import ClientSerializer, RateCardSerializer, QuoteSerializer
import decimal

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

class RateCardViewSet(viewsets.ModelViewSet):
    queryset = RateCard.objects.all()
    serializer_class = RateCardSerializer

class QuoteViewSet(viewsets.ModelViewSet):
    queryset = Quote.objects.all()
    serializer_class = QuoteSerializer


    VOLUMETRIC_FACTOR = decimal.Decimal('167')

    def create(self, request, *args, **kwargs):
        data = request.data

        # --- 1. Calculate Chargeable Weight ---
        raw_actual_weight = data.get('actual_weight_kg', 0)
        raw_volume_cbm = data.get('volume_cbm', 0)
        try:
            actual_weight = decimal.Decimal(str(raw_actual_weight))
            volume_cbm = decimal.Decimal(str(raw_volume_cbm))
        except (decimal.InvalidOperation, TypeError):
            return Response(
                {"error": "Invalid numeric input for actual_weight_kg or volume_cbm."},
                status=status.HTTP_400_BAD_REQUEST
            )
        volumetric_weight = volume_cbm * self.VOLUMETRIC_FACTOR
        chargeable_weight = max(actual_weight, volumetric_weight)

        # --- 2. Find the Correct Rate Card ---
        try:
            rate_card = RateCard.objects.get(
                origin=data.get('origin'), 
                destination=data.get('destination')
            )
        except RateCard.DoesNotExist:
            return Response(
                {"error": "No rate card found for the specified route."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- 3. Select the Rate from Weight Breaks ---
        rate_per_kg = decimal.Decimal(0)
        if chargeable_weight >= 1000:
            rate_per_kg = rate_card.brk_1000
        elif chargeable_weight >= 500:
            rate_per_kg = rate_card.brk_500
        elif chargeable_weight >= 250:
            rate_per_kg = rate_card.brk_250
        elif chargeable_weight >= 100:
            rate_per_kg = rate_card.brk_100
        else:
            rate_per_kg = rate_card.brk_45        # --- 4. Calculate Costs and Totals ---
        base_cost = max(chargeable_weight * rate_per_kg, rate_card.min_charge)
        margin_pct = decimal.Decimal(data.get('margin_pct', 20.0)) / 100
        total_sell = base_cost * (1 + margin_pct)

    # --- 5. Prepare the Final Data to Save ---
    allowed_fields = ['client', 'origin', 'destination', 'mode', 'actual_weight_kg', 'volume_cbm', 'margin_pct']
    final_quote_data = {field: data.get(field) for field in allowed_fields if field in data}
    # Set computed fields server-side
    final_quote_data['chargeable_weight_kg'] = chargeable_weight.quantize(decimal.Decimal('0.01'))
    final_quote_data['rate_used_per_kg'] = rate_per_kg.quantize(decimal.Decimal('0.01'))
    final_quote_data['base_cost'] = base_cost.quantize(decimal.Decimal('0.01'))
    final_quote_data['total_sell'] = total_sell.quantize(decimal.Decimal('0.01'))

    serializer = self.get_serializer(data=final_quote_data)
    serializer.is_valid(raise_exception=True)
    self.perform_create(serializer)

    headers = self.get_success_headers(serializer.data)
    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)