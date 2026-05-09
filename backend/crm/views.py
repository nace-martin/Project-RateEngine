from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Interaction, Opportunity
from .serializers import InteractionSerializer, OpportunitySerializer
from .services import mark_opportunity_lost, mark_opportunity_won


class CrmWritePermission(permissions.BasePermission):
    message = "Only sales, manager, or admin users can modify CRM records."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, "role", None) in {"sales", "manager", "admin"}


class OpportunityViewSet(viewsets.ModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [permissions.IsAuthenticated, CrmWritePermission]

    def get_queryset(self):
        queryset = Opportunity.objects.select_related("company", "owner", "won_by").filter(is_active=True)
        company = self.request.query_params.get("company")
        status = self.request.query_params.get("status")
        owner = self.request.query_params.get("owner")
        service_type = self.request.query_params.get("service_type")
        priority = self.request.query_params.get("priority")
        if company:
            queryset = queryset.filter(company_id=company)
        if status:
            queryset = queryset.filter(status=status.upper())
        if owner:
            queryset = queryset.filter(owner_id=owner)
        if service_type:
            queryset = queryset.filter(service_type=service_type.upper())
        if priority:
            queryset = queryset.filter(priority=priority.upper())
        return queryset.order_by("-updated_at", "-created_at")

    def perform_create(self, serializer):
        owner = serializer.validated_data.get("owner") or self.request.user
        serializer.save(owner=owner)

    @action(detail=True, methods=["post"])
    def mark_qualified(self, request, pk=None):
        opportunity = self.get_object()
        opportunity.status = Opportunity.Status.QUALIFIED
        opportunity.lost_reason = ""
        opportunity.save(update_fields=["status", "lost_reason", "updated_at"])
        serializer = self.get_serializer(opportunity)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_won(self, request, pk=None):
        opportunity = self.get_object()
        opportunity = mark_opportunity_won(
            opportunity,
            actor=request.user,
            reason=request.data.get("won_reason", ""),
            source_type="MANUAL",
        )
        serializer = self.get_serializer(opportunity)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_lost(self, request, pk=None):
        lost_reason = str(request.data.get("lost_reason", "")).strip()
        if not lost_reason:
            return Response(
                {"lost_reason": ["Lost reason is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        opportunity = self.get_object()
        opportunity = mark_opportunity_lost(opportunity, actor=request.user, reason=lost_reason)
        serializer = self.get_serializer(opportunity)
        return Response(serializer.data)


class InteractionViewSet(viewsets.ModelViewSet):
    serializer_class = InteractionSerializer
    permission_classes = [permissions.IsAuthenticated, CrmWritePermission]

    def get_queryset(self):
        queryset = Interaction.objects.select_related("company", "contact", "opportunity", "author")
        company = self.request.query_params.get("company")
        opportunity = self.request.query_params.get("opportunity")
        if company:
            queryset = queryset.filter(company_id=company)
        if opportunity:
            queryset = queryset.filter(opportunity_id=opportunity)
        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
