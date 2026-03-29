# backend/parties/serializers.py

from rest_framework import serializers

from core.security import validate_image_upload
from parties.branding_urls import build_public_branding_logo_url

from .models import Company, Contact, OrganizationBranding

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


class OrganizationBrandingSettingsSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    logo_primary_url = serializers.SerializerMethodField()
    logo_small_url = serializers.SerializerMethodField()
    clear_primary_logo = serializers.BooleanField(required=False, write_only=True)
    clear_small_logo = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = OrganizationBranding
        fields = [
            "organization_name",
            "organization_slug",
            "display_name",
            "legal_name",
            "support_email",
            "support_phone",
            "website_url",
            "address_lines",
            "quote_footer_text",
            "public_quote_tagline",
            "email_signature_text",
            "primary_color",
            "accent_color",
            "logo_primary",
            "logo_primary_url",
            "logo_small",
            "logo_small_url",
            "is_active",
            "clear_primary_logo",
            "clear_small_logo",
        ]
        extra_kwargs = {
            "logo_primary": {"required": False, "allow_null": True},
            "logo_small": {"required": False, "allow_null": True},
            "display_name": {"required": False},
            "legal_name": {"required": False},
            "support_email": {"required": False},
            "support_phone": {"required": False},
            "website_url": {"required": False},
            "address_lines": {"required": False},
            "quote_footer_text": {"required": False},
            "public_quote_tagline": {"required": False},
            "email_signature_text": {"required": False},
            "primary_color": {"required": False},
            "accent_color": {"required": False},
            "is_active": {"required": False},
        }

    def get_logo_primary_url(self, obj):
        if not obj.logo_primary:
            return None
        return build_public_branding_logo_url(obj, "primary", request=self.context.get("request"))

    def get_logo_small_url(self, obj):
        if not obj.logo_small:
            return None
        return build_public_branding_logo_url(obj, "small", request=self.context.get("request"))

    def validate_logo_primary(self, value):
        if value:
            validate_image_upload(value)
        return value

    def validate_logo_small(self, value):
        if value:
            validate_image_upload(value)
        return value

    def update(self, instance, validated_data):
        if validated_data.pop("clear_primary_logo", False):
            instance.logo_primary = None
        if validated_data.pop("clear_small_logo", False):
            instance.logo_small = None
        return super().update(instance, validated_data)
