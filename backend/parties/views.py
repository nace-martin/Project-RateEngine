"""
V3 API views for the parties app.
"""

import os

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from rest_framework import generics, permissions, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission
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
from core.storage_utils import file_field_basename, file_field_storage_exists


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


def resolve_active_organization(user=None) -> Organization:
    user_organization = getattr(user, "organization", None)
    if user_organization and user_organization.is_active:
        return user_organization
    if user_organization:
        return user_organization

    # Deterministic selection for parent/global organization (e.g. slug="efm" or name="Express Freight Management" / "EFM")
    # TODO: Formalize tenant/department brand hierarchy in the database model (e.g. adding is_parent or parent_organization foreign key).
    
    # 1. Try active parent organization by slug or name
    parent_org = (
        Organization.objects.filter(slug="efm", is_active=True).first()
        or Organization.objects.filter(name__in=["Express Freight Management", "EFM"], is_active=True).first()
    )
    if parent_org:
        return parent_org

    # 2. Try any active organization other than the department-specific Express Air Cargo
    other_org = Organization.objects.filter(is_active=True).exclude(slug="efm-express-air-cargo").order_by("name").first()
    if other_org:
        return other_org

    # 3. Fallback to Express Air Cargo if it is the only active organization
    fallback_org = Organization.objects.filter(slug="efm-express-air-cargo", is_active=True).first()
    if fallback_org:
        return fallback_org

    # 4. Try any active organization as a final fallback
    any_active = Organization.objects.filter(is_active=True).order_by("name").first()
    if any_active:
        return any_active

    # 5. Handle cases where no active organizations exist by looking at inactive ones
    any_inactive = (
        Organization.objects.filter(slug="efm").first()
        or Organization.objects.filter(name__in=["Express Freight Management", "EFM"]).first()
        or Organization.objects.exclude(slug="efm-express-air-cargo").order_by("name").first()
        or Organization.objects.filter(slug="efm-express-air-cargo").first()
        or Organization.objects.order_by("name").first()
    )
    if any_inactive:
        return any_inactive

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
        organization = resolve_active_organization(self.request.user)
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


class PublicOrganizationBrandingLogoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, organization_slug: str, variant: str):
        organization = get_object_or_404(Organization, slug=organization_slug, is_active=True)
        branding = getattr(organization, "branding", None)
        if branding is None or not branding.is_active:
            raise Http404("Branding not found.")

        logo_field = branding.logo_primary if variant == "primary" else branding.logo_small if variant == "small" else None
        if not logo_field:
            raise Http404("Logo not found.")

        if not file_field_storage_exists(logo_field):
            raise Http404("Logo file not found.")

        content_type = "image/png"
        file_name = file_field_basename(logo_field)
        lower_name = file_name.lower()
        if lower_name.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif lower_name.endswith(".gif"):
            content_type = "image/gif"
        elif lower_name.endswith(".webp"):
            content_type = "image/webp"

        response = FileResponse(logo_field.storage.open(logo_field.name, "rb"), content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{file_name}"'
        response["Cache-Control"] = "public, max-age=300"
        return response


class PublicBrandingView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            organization = resolve_active_organization()
            branding, _ = OrganizationBranding.objects.get_or_create(
                organization=organization,
                defaults={
                    "display_name": organization.name,
                    "is_active": True,
                },
            )
            serializer = OrganizationBrandingSettingsSerializer(
                branding,
                context={"request": request},
            )
            return Response(serializer.data)
        except Organization.DoesNotExist:
            return Response({"detail": "No organization configured."}, status=404)
