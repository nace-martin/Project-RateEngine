# backend/parties/serializers.py

from rest_framework import serializers
from .models import Company, Contact

class CustomerV3Serializer(serializers.ModelSerializer):
    """Serialize customer companies for the v3 API."""

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "is_customer",
            "is_agent",
            "is_carrier",
            "tax_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        """Ensure consistency if needed."""
        # Example validation: Must be at least ONE of the roles?
        # For now, lax validation is fine.
        return data


class CompanySearchV3Serializer(serializers.ModelSerializer):
    """Lightweight serializer for search results."""

    class Meta:
        model = Company
        fields = ["id", "name"]


class ContactV3Serializer(serializers.ModelSerializer):
    """Serialize contacts associated with a company."""

    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Contact
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "is_primary",
            "company",
            "company_name",
        ]
        read_only_fields = ["id", "company", "company_name"]