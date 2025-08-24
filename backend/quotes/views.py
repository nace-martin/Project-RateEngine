from rest_framework import viewsets
from .models import Client, RateCard, Quote
from .serializers import ClientSerializer, RateCardSerializer, QuoteSerializer

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

class RateCardViewSet(viewsets.ModelViewSet):
    queryset = RateCard.objects.all()
    serializer_class = RateCardSerializer

class QuoteViewSet(viewsets.ModelViewSet):
    queryset = Quote.objects.all()
    serializer_class = QuoteSerializer