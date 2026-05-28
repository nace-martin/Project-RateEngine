# backend/quotes/migrations/0037_seed_parent_organization.py

import os
import django.db.models.deletion
from django.db import migrations, models
from django.core.files import File
from django.conf import settings


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

    branding, _ = OrganizationBranding.objects.get_or_create(
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

    # Copy and save the correct EFM static logo from backend/static/images/efm_logo_new.png
    static_logo_path = os.path.join(settings.BASE_DIR, "static", "images", "efm_logo_new.png")
    if os.path.exists(static_logo_path):
        if not branding.logo_small:
            with open(static_logo_path, "rb") as f:
                branding.logo_small.save("efm_logo_new.png", File(f), save=True)
        if not branding.logo_primary:
            with open(static_logo_path, "rb") as f:
                branding.logo_primary.save("efm_logo_new.png", File(f), save=True)


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
