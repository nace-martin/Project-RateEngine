from django.db.models import Q
from django.http import HttpResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Shipment, ShipmentAddressBookEntry, ShipmentTemplate
from .pdf_service import generate_shipment_pdf
from .serializers import (
    ShipmentAddressBookEntrySerializer,
    ShipmentListSerializer,
    ShipmentSerializer,
    ShipmentSettingsSerializer,
    ShipmentTemplateSerializer,
)
from .services import (
    cancel_shipment,
    duplicate_shipment,
    finalize_shipment,
    get_or_create_shipment_settings,
    persist_generated_pdf,
)


class ShipmentWritePermission(permissions.BasePermission):
    message = "Only sales, manager, or admin users can modify shipments."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role in {"sales", "manager", "admin"}


class ShipmentAdminPermission(permissions.BasePermission):
    message = "Admin access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


class OrganizationScopedMixin:
    def get_organization(self):
        return getattr(self.request.user, "organization", None)


class ShipmentViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, ShipmentWritePermission]

    def _require_roles(self, request, allowed_roles, message):
        if getattr(request.user, "role", None) not in allowed_roles:
            raise PermissionDenied(message)

    def get_queryset(self):
        organization = self.get_organization()
        queryset = (
            Shipment.objects.filter(organization=organization)
            .select_related("origin_location", "destination_location", "created_by", "organization")
            .prefetch_related("pieces", "charges", "documents", "events")
        )
        query = self.request.query_params.get("q", "").strip()
        status_filter = self.request.query_params.get("status", "").strip().upper()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if query:
            queryset = queryset.filter(
                Q(connote_number__icontains=query)
                | Q(reference_number__icontains=query)
                | Q(shipper_company_name__icontains=query)
                | Q(consignee_company_name__icontains=query)
                | Q(origin_code__icontains=query)
                | Q(destination_code__icontains=query)
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ShipmentListSerializer
        return ShipmentSerializer

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        self._require_roles(
            request,
            {"sales", "manager", "admin"},
            "Only sales, manager, or admin users can finalize shipments.",
        )
        shipment = self.get_object()
        if shipment.status == Shipment.Status.FINALIZED:
            return Response(ShipmentSerializer(shipment, context={"request": request}).data)
        serializer = ShipmentSerializer(
            shipment,
            data=request.data or {},
            partial=True,
            context={**self.get_serializer_context(), "for_finalize": True},
        )
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save()
        try:
            shipment = finalize_shipment(shipment, user=request.user)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(ShipmentSerializer(shipment, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        self._require_roles(
            request,
            {"sales", "manager", "admin"},
            "Only sales, manager, or admin users can duplicate draft shipments.",
        )
        shipment = self.get_object()
        try:
            duplicate = duplicate_shipment(shipment, user=request.user, reissue=False)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(ShipmentSerializer(duplicate, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self._require_roles(
            request,
            {"manager", "admin"},
            "Only manager or admin users can cancel shipments.",
        )
        shipment = self.get_object()
        reason = str(request.data.get("reason", "")).strip()
        try:
            shipment = cancel_shipment(shipment, reason=reason, user=request.user)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(ShipmentSerializer(shipment, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def reissue(self, request, pk=None):
        self._require_roles(
            request,
            {"manager", "admin"},
            "Only manager or admin users can reissue finalized shipments.",
        )
        shipment = self.get_object()
        try:
            reissued = duplicate_shipment(shipment, user=request.user, reissue=True)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(ShipmentSerializer(reissued, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        self._require_roles(
            request,
            {"sales", "manager", "admin"},
            "Only sales, manager, or admin users can print or reprint shipment connotes.",
        )
        shipment = self.get_object()
        if shipment.status == Shipment.Status.DRAFT:
            serializer = ShipmentSerializer(
                shipment,
                data={},
                partial=True,
                context={**self.get_serializer_context(), "for_finalize": True},
            )
            serializer.is_valid(raise_exception=True)
            try:
                shipment = finalize_shipment(shipment, user=request.user)
            except ValueError as exc:
                raise ValidationError(str(exc))
        elif shipment.status != Shipment.Status.FINALIZED:
            raise ValidationError("Only draft or finalized shipments can generate or reprint connotes.")
        pdf_bytes = generate_shipment_pdf(shipment)
        file_name = f"{shipment.connote_number or shipment.id}.pdf"
        persist_generated_pdf(shipment, pdf_bytes, file_name, user=request.user)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name}"'
        return response


class ShipmentAddressBookViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    serializer_class = ShipmentAddressBookEntrySerializer
    permission_classes = [permissions.IsAuthenticated, ShipmentWritePermission]

    def get_queryset(self):
        queryset = (
            ShipmentAddressBookEntry.objects.filter(organization=self.get_organization())
            .select_related("company", "contact")
            .order_by("label", "company_name")
        )
        role = self.request.query_params.get("party_role", "").strip().upper()
        if role:
            queryset = queryset.filter(party_role__in=[role, ShipmentAddressBookEntry.PartyRole.BOTH])
        return queryset

    def perform_create(self, serializer):
        serializer.save(
            organization=self.get_organization(),
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ShipmentTemplateViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    serializer_class = ShipmentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, ShipmentWritePermission]

    def get_queryset(self):
        return ShipmentTemplate.objects.filter(organization=self.get_organization()).order_by("name")

    def perform_create(self, serializer):
        serializer.save(
            organization=self.get_organization(),
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ShipmentSettingsAPIView(OrganizationScopedMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, ShipmentAdminPermission]

    def get(self, request):
        settings_obj = get_or_create_shipment_settings(self.get_organization())
        return Response(ShipmentSettingsSerializer(settings_obj).data)

    def patch(self, request):
        settings_obj = get_or_create_shipment_settings(self.get_organization())
        serializer = ShipmentSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(updated_by=request.user)
        return Response(ShipmentSettingsSerializer(updated).data)
