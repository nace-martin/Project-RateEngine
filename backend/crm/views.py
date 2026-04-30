from rest_framework import permissions, viewsets

from .models import Interaction, Opportunity, Task
from .serializers import InteractionSerializer, OpportunitySerializer, TaskSerializer


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


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated, CrmWritePermission]

    def get_queryset(self):
        queryset = Task.objects.select_related("company", "opportunity", "owner", "completed_by")
        owner = self.request.query_params.get("owner")
        status = self.request.query_params.get("status")
        due_date = self.request.query_params.get("due_date")
        company = self.request.query_params.get("company")
        opportunity = self.request.query_params.get("opportunity")
        if owner:
            queryset = queryset.filter(owner_id=owner)
        if status:
            queryset = queryset.filter(status=status.upper())
        if due_date:
            queryset = queryset.filter(due_date=due_date)
        if company:
            queryset = queryset.filter(company_id=company)
        if opportunity:
            queryset = queryset.filter(opportunity_id=opportunity)
        return queryset.order_by("due_date", "-created_at")

    def perform_create(self, serializer):
        owner = serializer.validated_data.get("owner") or self.request.user
        serializer.save(owner=owner)
