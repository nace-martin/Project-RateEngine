from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


GENERAL_DEPARTMENT = "GENERAL"


def _get_default_organization(Organization):
    organization = (
        Organization.objects
        .filter(is_active=True)
        .exclude(slug="default-organization")
        .order_by("name")
        .first()
    )
    if organization is None:
        organization = Organization.objects.filter(is_active=True).order_by("name").first()
    if organization is None:
        organization = (
            Organization.objects
            .exclude(slug="default-organization")
            .order_by("name")
            .first()
        )
    if organization is None:
        organization = Organization.objects.order_by("name").first()
    if organization is None:
        organization = Organization.objects.create(
            name="Default Organization",
            slug="default-organization",
            is_active=True,
        )
    return organization


def backfill_user_hierarchy(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    Organization = apps.get_model("parties", "Organization")

    default_organization = _get_default_organization(Organization)

    CustomUser.objects.filter(organization__isnull=True).update(organization=default_organization)
    CustomUser.objects.filter(Q(department__isnull=True) | Q(department="")).update(
        department=GENERAL_DEPARTMENT
    )


def revert_user_hierarchy_backfill(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    CustomUser.objects.filter(department=GENERAL_DEPARTMENT).update(department="")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_customuser_organization"),
    ]

    operations = [
        migrations.RunPython(backfill_user_hierarchy, revert_user_hierarchy_backfill),
        migrations.AlterField(
            model_name="customuser",
            name="department",
            field=models.CharField(
                choices=[
                    ("GENERAL", "General"),
                    ("AIR", "Air Freight"),
                    ("SEA", "Sea Freight"),
                    ("LAND", "Land Freight"),
                ],
                default="GENERAL",
                help_text="Department assignment for visibility restrictions (e.g., Air vs Sea).",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="organization",
            field=models.ForeignKey(
                help_text="Tenant/account workspace this user belongs to.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="parties.organization",
            ),
        ),
    ]
