from django.db import migrations, models
import django.db.models.deletion


def assign_default_organization(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    Organization = apps.get_model("parties", "Organization")

    organization = Organization.objects.filter(is_active=True).order_by("name").first()
    if organization is None:
        organization = Organization.objects.order_by("name").first()
    if organization is None:
        return

    CustomUser.objects.filter(organization__isnull=True).update(organization=organization)


def unassign_default_organization(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    CustomUser.objects.update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ("parties", "0006_organization_organizationbranding"),
        ("accounts", "0003_customuser_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="Tenant/account workspace this user belongs to.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="parties.organization",
            ),
        ),
        migrations.RunPython(assign_default_organization, unassign_default_organization),
    ]
