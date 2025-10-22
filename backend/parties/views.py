# backend/parties/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status # Add status import
from .models import Company, Contact # Add Contact
from .serializers import CompanySearchSerializer, ContactSerializer # Add ContactSerializer

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

# --- ADD THIS NEW VIEW ---
class CompanyContactListAPIView(APIView):
    """
    Retrieves a list of contacts for a specific company ID.
    e.g., /api/v2/parties/companies/{company_id}/contacts/
    """
    def get(self, request, company_id, *args, **kwargs):
        try:
            # Ensure the company exists first
            company = Company.objects.get(id=company_id)
            contacts = Contact.objects.filter(company=company)
            serializer = ContactSerializer(contacts, many=True)
            return Response(serializer.data)
        except Company.DoesNotExist:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
             # Log the error e for debugging
            print(f"Error fetching contacts: {e}")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)