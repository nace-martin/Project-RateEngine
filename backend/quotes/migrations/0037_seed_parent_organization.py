# backend/quotes/migrations/0037_seed_parent_organization.py

import django.db.models.deletion
from django.db import migrations, models


def seed_parent_organization(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    Organization = apps.get_model("parties", "Organization")
    OrganizationBranding = apps.get_model("parties", "OrganizationBranding")

    pgk = Currency.objects.filter(code="PGK").first()
    organization, _ = Organization.objects.get_or_create(
        slug="efm",
        defaults={
            "name": "Express Freight Management",
            "is_active": True,
            "default_currency": pgk,
            "time_zone": "Pacific/Port_Moresby",
        },
    )

    if pgk and organization.default_currency_id is None:
        organization.default_currency = pgk
        organization.save(update_fields=["default_currency", "updated_at"])

    OrganizationBranding.objects.get_or_create(
        organization=organization,
        defaults={
            "display_name": "Express Freight Management",
            "legal_name": "Express Freight Management Ltd",
            "primary_color": "#0F2A56",
            "accent_color": "#D71920",
            "support_email": "info@efmexpress.com",
            "support_phone": "+675 325 8500",
            "website_url": "https://www.efmexpress.com",
            "address_lines": "PO Box 1791\nPort Moresby\nPapua New Guinea",
            "quote_footer_text": (
                "Valid until quoted expiry. Space subject to availability at time of booking."
            ),
            "public_quote_tagline": "Freight forwarder and logistics solutions from Express Freight Management",
            "email_signature_text": (
                "Express Freight Management\n"
                "Phone: +675 325 8500\n"
                "Email: info@efmexpress.com"
            ),
            "is_active": True,
        },
    )


def unseed_parent_organization(apps, schema_editor):
    Organization = apps.get_model("parties", "Organization")
    organization = Organization.objects.filter(slug="efm").first()
    if organization:
        organization.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0036_quote_opportunity'),
    ]

    operations = [
        migrations.RunPython(seed_parent_organization, unseed_parent_organization),
    ]
