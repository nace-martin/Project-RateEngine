"""
V3 API views for the parties app.
"""

from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from rest_framework import generics, permissions, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Address, Company, Contact, Organization, OrganizationBranding
from .serializers import (
    CompanySearchV3Serializer,
    ContactV3Serializer,
    CustomerV3Serializer,
    OrganizationBrandingSettingsSerializer,
)
from accounts.models import CustomUser


class CustomerAccessPermission(BasePermission):
    """
    Custom permission for Customer management:
    - All authenticated users can READ (list, retrieve)
    - Only Admin users can CREATE/UPDATE/DELETE
    
    This protects data quality by restricting who can modify customer records.
    """
    message = "Admin access required to create or edit customers."
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # All authenticated users can read
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # For write methods, only Admin allowed
        return request.user.role == CustomUser.ROLE_ADMIN


class SystemSettingsPermission(BasePermission):
    message = "Admin access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == CustomUser.ROLE_ADMIN)


def resolve_active_organization() -> Organization:
    organization = Organization.objects.filter(is_active=True).order_by("name").first()
    if organization:
        return organization
    organization = Organization.objects.order_by("name").first()
    if organization:
        return organization
    raise Organization.DoesNotExist("No organization configured.")


class CustomerV3ViewSet(viewsets.ModelViewSet):
    """
    V3 ViewSet for managing customer companies.
    
    Permissions:
    - GET (list/retrieve): All authenticated users
    - POST/PUT/PATCH/DELETE: Admin only
    """

    serializer_class = CustomerV3Serializer
    permission_classes = [permissions.IsAuthenticated, CustomerAccessPermission]
    http_method_names = ["get", "post", "put", "patch"]

    def get_queryset(self):
        customer_filter = Q(is_customer=True) | Q(company_type="CUSTOMER")
        return (
            Company.objects.filter(customer_filter, is_active=True)
            .order_by("name")
            .prefetch_related(
                Prefetch(
                    "contacts",
                    queryset=Contact.objects.filter(is_active=True).order_by(
                        "-is_primary", "last_name", "first_name"
                    ),
                ),
                Prefetch(
                    "addresses",
                    queryset=Address.objects.select_related("city__country", "country").order_by(
                        "-is_primary", "id"
                    ),
                ),
            )
        )

    def perform_create(self, serializer):
        serializer.save(is_customer=True)

    def perform_update(self, serializer):
        serializer.save(is_customer=True)


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
        return (
            Company.objects.filter(name__icontains=query, is_active=True)
            .filter(Q(is_customer=True) | Q(company_type="CUSTOMER"))
            .order_by("name")[:20]
        )


class CompanyContactListV3View(generics.ListAPIView):
    """
    V3 endpoint listing contacts for a specific company.
    """

    serializer_class = ContactV3Serializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        company_id = self.kwargs.get("company_id")
        company = get_object_or_404(Company, pk=company_id)
        return company.contacts.filter(is_active=True).order_by("last_name", "first_name")


class OrganizationBrandingSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated, SystemSettingsPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self) -> OrganizationBranding:
        organization = resolve_active_organization()
        branding, _ = OrganizationBranding.objects.get_or_create(
            organization=organization,
            defaults={
                "display_name": organization.name,
                "is_active": True,
            },
        )
        return branding

    def get(self, request):
        serializer = OrganizationBrandingSettingsSerializer(
            self.get_object(),
            context={"request": request},
        )
        return Response(serializer.data)

    def patch(self, request):
        branding = self.get_object()
        serializer = OrganizationBrandingSettingsSerializer(
            branding,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
