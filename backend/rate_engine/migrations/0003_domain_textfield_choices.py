from django.db import migrations, models


def normalize_choices(apps, schema_editor):
    Providers = apps.get_model('rate_engine', 'Providers')
    for provider in Providers.objects.all():
        if provider.provider_type:
            provider.provider_type = provider.provider_type.upper()
            provider.save(update_fields=['provider_type'])
    Ratecards = apps.get_model('rate_engine', 'Ratecards')
    for rc in Ratecards.objects.all():
        updated = False
        if rc.role:
            rc.role = rc.role.upper()
            updated = True
        if rc.scope:
            rc.scope = rc.scope.upper()
            updated = True
        if rc.direction:
            rc.direction = rc.direction.upper()
            updated = True
        if updated:
            rc.save(update_fields=['role', 'scope', 'direction'])


class Migration(migrations.Migration):

    dependencies = [
        ('rate_engine', '0002_currency_rates_unique_rate_type'),
    ]

    operations = [
        migrations.RunPython(normalize_choices, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='providers',
            name='provider_type',
            field=models.CharField(max_length=16, choices=[('AIR', 'Air'), ('AGENT', 'Agent'), ('CARRIER', 'Carrier')]),
        ),
        migrations.AlterField(
            model_name='ratecards',
            name='role',
            field=models.CharField(max_length=16, choices=[('BUY', 'Buy'), ('SELL', 'Sell')]),
        ),
        migrations.AlterField(
            model_name='ratecards',
            name='scope',
            field=models.CharField(max_length=16, choices=[('INTERNATIONAL', 'International'), ('DOMESTIC', 'Domestic')]),
        ),
        migrations.AlterField(
            model_name='ratecards',
            name='direction',
            field=models.CharField(max_length=16, choices=[('IMPORT', 'Import'), ('EXPORT', 'Export'), ('DOMESTIC', 'Domestic')]),
        ),
    ]
