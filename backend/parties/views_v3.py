"""
V3 API views for the parties app.
"""

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets

from .models import Company, Contact
from .serializers_v3 import (
    CustomerV3Serializer,
    CompanySearchV3Serializer,
    ContactV3Serializer,
)


class CustomerV3ViewSet(viewsets.ModelViewSet):
    """
    V3 ViewSet for managing customer companies.
    """

    serializer_class = CustomerV3Serializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch"]

    def get_queryset(self):
        return (
            Company.objects.filter(company_type="CUSTOMER")
            .order_by("name")
            .prefetch_related("contacts")
        )

    def perform_create(self, serializer):
        serializer.save(company_type="CUSTOMER")

    def perform_update(self, serializer):
        serializer.save(company_type="CUSTOMER")


class CompanyV3SearchView(generics.ListAPIView):
    """
    V3 endpoint for company search.
    """

    serializer_class = CompanySearchV3Serializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Company.objects.none()
        return Company.objects.filter(name__icontains=query).order_by("name")[:20]


class CompanyContactListV3View(generics.ListAPIView):
    """
    V3 endpoint listing contacts for a specific company.
    """

    serializer_class = ContactV3Serializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        company_id = self.kwargs.get("company_id")
        company = get_object_or_404(Company, pk=company_id)
        return company.contacts.all().order_by("last_name", "first_name")
