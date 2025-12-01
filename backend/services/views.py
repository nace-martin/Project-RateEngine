from rest_framework import viewsets
from .models import ServiceComponent
from .serializers import ServiceComponentSerializer

class ServiceComponentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceComponent.objects.all().order_by('code')
    serializer_class = ServiceComponentSerializer
