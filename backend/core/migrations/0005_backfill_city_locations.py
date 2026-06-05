from django.db import migrations


def create_city_locations(apps, schema_editor):
    Location = apps.get_model('core', 'Location')
    City = apps.get_model('core', 'City')

    existing_city_ids = set(
        Location.objects.filter(kind='CITY', city__isnull=False)
        .values_list('city_id', flat=True)
    )

    to_create = []
    seen_city_ids = set()

    for city in City.objects.select_related('country'):
        if city.id not in existing_city_ids and city.id not in seen_city_ids:
            to_create.append(
                Location(
                    kind='CITY',
                    city=city,
                    name=city.name,
                    code=city.name[:3].upper(),
                    country=city.country,
                )
            )
            seen_city_ids.add(city.id)

    if to_create:
        Location.objects.bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_backfill_locations'),
    ]

    operations = [
        migrations.RunPython(create_city_locations, migrations.RunPython.noop),
    ]
