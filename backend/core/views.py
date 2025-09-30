from rest_framework import viewsets
from .models import Station
from .serializers import StationSerializer

class StationViewSet(viewsets.ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer
