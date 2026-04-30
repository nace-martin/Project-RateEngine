from django.utils import timezone
from rest_framework import serializers

from .models import Interaction, Opportunity, Task


class OpportunitySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    won_by_username = serializers.CharField(source="won_by.username", read_only=True)

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "company",
            "company_name",
            "title",
            "service_type",
            "direction",
            "scope",
            "origin",
            "destination",
            "estimated_weight_kg",
            "estimated_volume_cbm",
            "estimated_fcl_count",
            "estimated_frequency",
            "estimated_revenue",
            "estimated_currency",
            "status",
            "priority",
            "owner",
            "owner_username",
            "next_action",
            "next_action_date",
            "last_activity_at",
            "won_at",
            "won_by",
            "won_by_username",
            "won_reason",
            "lost_reason",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_activity_at", "won_at", "won_by", "created_at", "updated_at"]
        extra_kwargs = {"owner": {"required": False, "allow_null": True}}


class InteractionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    author_username = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Interaction
        fields = [
            "id",
            "company",
            "company_name",
            "contact",
            "opportunity",
            "author",
            "author_username",
            "interaction_type",
            "summary",
            "outcomes",
            "next_action",
            "next_action_date",
            "is_system_generated",
            "system_event_type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "is_system_generated",
            "system_event_type",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        company = attrs.get("company", getattr(instance, "company", None))
        contact = attrs.get("contact", getattr(instance, "contact", None))
        opportunity = attrs.get("opportunity", getattr(instance, "opportunity", None))
        if contact and company and contact.company_id != company.id:
            raise serializers.ValidationError({"contact": "Selected contact does not belong to the selected company."})
        if opportunity and company and opportunity.company_id != company.id:
            raise serializers.ValidationError({"opportunity": "Selected opportunity does not belong to the selected company."})
        return attrs


class TaskSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    completed_by_username = serializers.CharField(source="completed_by.username", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "company",
            "opportunity",
            "description",
            "owner",
            "owner_username",
            "due_date",
            "status",
            "completed_at",
            "completed_by",
            "completed_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "completed_at", "completed_by", "created_at", "updated_at"]
        extra_kwargs = {"owner": {"required": False}}

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        company = attrs.get("company", getattr(instance, "company", None))
        opportunity = attrs.get("opportunity", getattr(instance, "opportunity", None))
        if not company and not opportunity:
            raise serializers.ValidationError("Task must link to at least a company or opportunity.")
        if company and opportunity and opportunity.company_id != company.id:
            raise serializers.ValidationError({"opportunity": "Selected opportunity does not belong to the selected company."})
        return attrs

    def create(self, validated_data):
        if validated_data.get("opportunity") and not validated_data.get("company"):
            validated_data["company"] = validated_data["opportunity"].company
        if validated_data.get("status") == Task.Status.COMPLETED:
            request = self.context.get("request")
            validated_data["completed_at"] = timezone.now()
            validated_data["completed_by"] = getattr(request, "user", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        prior_status = instance.status
        if validated_data.get("opportunity") and not validated_data.get("company", instance.company):
            validated_data["company"] = validated_data["opportunity"].company
        if validated_data.get("status") == Task.Status.COMPLETED and prior_status != Task.Status.COMPLETED:
            request = self.context.get("request")
            validated_data["completed_at"] = timezone.now()
            validated_data["completed_by"] = getattr(request, "user", None)
        return super().update(instance, validated_data)
