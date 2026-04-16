from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


GENERAL_DEPARTMENT = "GENERAL"
DEPARTMENT_REMAP = {
    "AIR": "AIR_FREIGHT",
    "SEA": "SEA_FREIGHT",
    "LAND": "LAND_FREIGHT",
}
VALID_DEPARTMENTS = {
    "AIR_FREIGHT",
    "SEA_FREIGHT",
    "LAND_FREIGHT",
    "CUSTOMS",
    GENERAL_DEPARTMENT,
}


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
    for old_value, new_value in DEPARTMENT_REMAP.items():
        CustomUser.objects.filter(department=old_value).update(department=new_value)
    CustomUser.objects.filter(
        Q(department__isnull=True) | Q(department="") | ~Q(department__in=VALID_DEPARTMENTS)
    ).update(department=GENERAL_DEPARTMENT)


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
                    ("AIR_FREIGHT", "Air Freight"),
                    ("SEA_FREIGHT", "Sea Freight"),
                    ("LAND_FREIGHT", "Land Freight"),
                    ("CUSTOMS", "Customs"),
                    ("GENERAL", "General"),
                ],
                default="GENERAL",
                help_text="Department assignment for visibility restrictions (e.g., Air vs Sea).",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="organization",
            field=models.ForeignKey(
                blank=False,
                help_text="Tenant/account workspace this user belongs to.",
                null=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="parties.organization",
            ),
        ),
    ]
