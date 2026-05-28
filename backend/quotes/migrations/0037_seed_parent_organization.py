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

    branding, created = OrganizationBranding.objects.get_or_create(
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

    if not created:
        branding.display_name = "Express Freight Management"
        branding.legal_name = "Express Freight Management Ltd"
        branding.primary_color = "#0F2A56"
        branding.accent_color = "#D71920"
        branding.support_email = "info@efmexpress.com"
        branding.support_phone = "+675 325 8500"
        branding.website_url = "https://www.efmexpress.com"
        branding.address_lines = "PO Box 1791\nPort Moresby\nPapua New Guinea"
        branding.quote_footer_text = "Valid until quoted expiry. Space subject to availability at time of booking."
        branding.public_quote_tagline = "Freight forwarder and logistics solutions from Express Freight Management"
        branding.email_signature_text = "Express Freight Management\nPhone: +675 325 8500\nEmail: info@efmexpress.com"
        branding.is_active = True
        branding.save(update_fields=[
            "display_name", "legal_name", "primary_color", "accent_color",
            "support_email", "support_phone", "website_url", "address_lines",
            "quote_footer_text", "public_quote_tagline", "email_signature_text", "is_active"
        ])

    # Copy and save the correct EFM static logo from backend/static/images/efm_logo_new.png
    static_logo_path = os.path.join(settings.BASE_DIR, "static", "images", "efm_logo_new.png")
    if os.path.exists(static_logo_path):
        # Unconditionally clear old logo files to prevent Django naming collision (e.g. efm_logo_new_xxxx.png)
        # and ensure the correct asset is freshly saved and used.
        if branding.logo_small:
            try:
                branding.logo_small.delete(save=False)
            except Exception:
                pass
        if branding.logo_primary:
            try:
                branding.logo_primary.delete(save=False)
            except Exception:
                pass

        with open(static_logo_path, "rb") as f:
            branding.logo_small.save("efm_logo_new.png", File(f), save=True)
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
