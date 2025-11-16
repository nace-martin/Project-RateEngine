from django.db import migrations


def create_city_locations(apps, schema_editor):
    Location = apps.get_model('core', 'Location')
    City = apps.get_model('core', 'City')

    for city in City.objects.select_related('country'):
        Location.objects.get_or_create(
            kind='CITY',
            city=city,
            defaults={
                'name': city.name,
                'code': city.name[:3].upper(),
                'country': city.country,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_backfill_locations'),
    ]

    operations = [
        migrations.RunPython(create_city_locations, migrations.RunPython.noop),
    ]
