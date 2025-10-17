# backend/parties/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Company
from .serializers import CompanySearchSerializer

class CompanySearchAPIView(APIView):
    """
    Provides a search endpoint for companies.
    Accepts a query parameter `q`.
    e.g., /api/v2/parties/search/?q=Test
    """
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '')
        if len(query) < 2:
            # Don't search for very short strings to avoid large results
            return Response([])

        # Case-insensitive search on the company name
        companies = Company.objects.filter(name__icontains=query)[:10]  # Limit to 10 results
        serializer = CompanySearchSerializer(companies, many=True)
        return Response(serializer.data)
