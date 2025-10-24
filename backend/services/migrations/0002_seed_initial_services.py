# backend/services/migrations/0002_seed_initial_services.py
from django.db import migrations

def seed_initial_services(apps, schema_editor):
    ServiceComponent = apps.get_model('services', 'ServiceComponent')

    ServiceComponent.objects.get_or_create(
        code="FRT_AIR",
        defaults={
            "description":"Freight",
            "mode":"AIR",
            "leg":"MAIN",
            "category":"TRANSPORT",
            "cost_type":"COGS",
            "cost_source":"EXPORT_RATECARD",
            "unit":"KG",
        }
    )

    ServiceComponent.objects.get_or_create(
        code="PKUP_ORG",
        defaults={
            "description":"Origin Pickup",
            "mode":"AIR",
            "leg":"ORIGIN",
            "category":"LOCAL",
            "cost_type":"COGS",
            "cost_source":"PARTNER_RATECARD",
            "unit":"KG",
        }
    )

class Migration(migrations.Migration):

    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_initial_services, migrations.RunPython.noop),
    ]
