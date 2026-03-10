# backend/parties/serializers.py

from rest_framework import serializers
from .models import Company, Contact

class CustomerV3Serializer(serializers.ModelSerializer):
    """Serialize customer companies for the v3 API."""
    company_name = serializers.CharField(source="name", required=False)
    contact_person_name = serializers.SerializerMethodField()
    primary_address = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "company_name",
            "is_active",
            "audience_type",
            "address_description",
            "contact_person_name",
            "primary_address",
            "is_customer",
            "is_agent",
            "is_carrier",
            "tax_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "contact_person_name",
            "primary_address",
            "created_at",
            "updated_at",
        ]

    def get_contact_person_name(self, obj: Company) -> str:
        contacts = list(obj.contacts.all())
        if not contacts:
            return ""
        primary = next((c for c in contacts if c.is_primary and c.is_active), None)
        contact = primary or next((c for c in contacts if c.is_active), None)
        if not contact:
            return ""
        return f"{contact.first_name} {contact.last_name}".strip()

    def get_primary_address(self, obj: Company) -> dict | None:
        addresses = list(obj.addresses.all())
        if not addresses:
            return None
        address = next((a for a in addresses if a.is_primary), None) or addresses[0]
        city_name = address.city.name if address.city else ""
        country_code = ""
        if address.country:
            country_code = address.country.code
        elif address.city and address.city.country:
            country_code = address.city.country.code
        return {
            "address_line_1": address.address_line_1,
            "address_line_2": address.address_line_2,
            "city": city_name,
            "state_province": "",
            "postcode": address.postal_code,
            "country": country_code,
        }

    def to_internal_value(self, data):
        # Backward compatibility for UI payloads that submit `company_name`.
        if isinstance(data, dict):
            normalized = data.copy()
            if not normalized.get("name") and normalized.get("company_name"):
                normalized["name"] = normalized["company_name"]
            data = normalized
        return super().to_internal_value(data)


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
            "is_active",
            "company",
            "company_name",
        ]
        read_only_fields = ["id", "company", "company_name"]
