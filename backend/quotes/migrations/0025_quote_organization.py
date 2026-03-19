import django.db.models.deletion
from django.db import migrations, models


def seed_default_organization(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    Organization = apps.get_model("parties", "Organization")
    OrganizationBranding = apps.get_model("parties", "OrganizationBranding")
    Quote = apps.get_model("quotes", "Quote")

    default_currency = Currency.objects.filter(code="PGK").first()
    organization, _ = Organization.objects.get_or_create(
        slug="efm-express-air-cargo",
        defaults={
            "name": "EFM Express Air Cargo",
            "is_active": True,
            "default_currency": default_currency,
            "time_zone": "Pacific/Port_Moresby",
        },
    )

    if default_currency and organization.default_currency_id is None:
        organization.default_currency = default_currency
        organization.save(update_fields=["default_currency", "updated_at"])

    OrganizationBranding.objects.get_or_create(
        organization=organization,
        defaults={
            "display_name": "EFM Express Air Cargo",
            "legal_name": "EFM Express Air Cargo",
            "primary_color": "#0F2A56",
            "accent_color": "#D71920",
            "support_email": "quotes@efmexpress.com",
            "support_phone": "+675 325 8500",
            "website_url": "https://www.efmexpress.com",
            "address_lines": "PO Box 1791\nPort Moresby\nPapua New Guinea",
            "quote_footer_text": (
                "Valid until quoted expiry. Space subject to availability at time of booking."
            ),
            "public_quote_tagline": "Air cargo quotations from EFM Express Air Cargo",
            "email_signature_text": (
                "EFM Express Air Cargo\n"
                "Phone: +675 325 8500\n"
                "Email: quotes@efmexpress.com"
            ),
            "is_active": True,
        },
    )

    Quote.objects.filter(organization__isnull=True).update(organization=organization)


def unseed_default_organization(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    Organization = apps.get_model("parties", "Organization")

    organization = Organization.objects.filter(slug="efm-express-air-cargo").first()
    if not organization:
        return

    Quote.objects.filter(organization=organization).update(organization=None)
    organization.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('parties', '0006_organization_organizationbranding'),
        ('quotes', '0024_spesourcebatchdb_spechargelinedb_source_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='quote',
            name='organization',
            field=models.ForeignKey(blank=True, help_text='Tenant/account branding context for this quote.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='quotes', to='parties.organization'),
        ),
        migrations.RunPython(seed_default_organization, unseed_default_organization),
    ]
