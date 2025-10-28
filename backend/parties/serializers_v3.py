"""
V3 serializers for the parties app.
Separated from legacy serializers to control the payload shape for the v3 API.
"""

from rest_framework import serializers

from .models import Company, Contact


class CustomerV3Serializer(serializers.ModelSerializer):
    """Serialize customer companies for the v3 API."""

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "company_type",
            "tax_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_company_type(self, value: str) -> str:
        """Ensure v3 customers always persist with the CUSTOMER company_type."""
        if value != "CUSTOMER":
            raise serializers.ValidationError("V3 customers must use company_type='CUSTOMER'.")
        return value


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
