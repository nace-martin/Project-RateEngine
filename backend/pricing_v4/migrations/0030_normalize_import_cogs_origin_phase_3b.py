from django.db import migrations


def normalize_origin_import_cogs(apps, schema_editor):
    ImportCOGS = apps.get_model('pricing_v4', 'ImportCOGS')
    # Target rows: scope=ORIGIN and destination_airport is set.
    # These are the 14 rows identified in Phase 3A as redundant.
    ImportCOGS.objects.filter(
        scope='ORIGIN',
        destination_airport__isnull=False
    ).update(destination_airport=None)


def reverse_normalization(apps, schema_editor):
    ImportCOGS = apps.get_model('pricing_v4', 'ImportCOGS')
    # Restore destination_airport = 'POM' for ORIGIN rows where it was cleared.
    # All 14 candidate rows from Phase 3A currently have destination_airport='POM'.
    ImportCOGS.objects.filter(
        scope='ORIGIN',
        destination_airport__isnull=True
    ).update(destination_airport='POM')


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0029_alter_importcogs_destination_airport_and_more'),
    ]

    operations = [
        migrations.RunPython(normalize_origin_import_cogs, reverse_normalization),
    ]
