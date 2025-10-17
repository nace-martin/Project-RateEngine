from rest_framework import viewsets
from .models import Quote
from .serializers import QuoteLegacyListSerializer

class QuoteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for viewing quotes.
    """
    queryset = Quote.objects.all().order_by('-created_at')
    serializer_class = QuoteLegacyListSerializer

    def list(self, request, *args, **kwargs):
        print("QuoteViewSet list method called")
        return super().list(request, *args, **kwargs)
