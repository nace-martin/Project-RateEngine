# backend/core/migrations/0002_seed_initial_data.py
from django.db import migrations

def seed_initial_data(apps, schema_editor):
    Country = apps.get_model('core', 'Country')
    City = apps.get_model('core', 'City')
    Airport = apps.get_model('core', 'Airport')

    australia = Country.objects.create(code='AU', name='Australia')
    papua_new_guinea = Country.objects.create(code='PG', name='Papua New Guinea')

    brisbane = City.objects.create(country=australia, name='Brisbane')
    sydney = City.objects.create(country=australia, name='Sydney')
    port_moresby = City.objects.create(country=papua_new_guinea, name='Port Moresby')

    Airport.objects.create(iata_code='BNE', name='Brisbane Airport', city=brisbane)
    Airport.objects.create(iata_code='SYD', name='Sydney Airport', city=sydney)
    Airport.objects.create(iata_code='POM', name='Port Moresby International Airport', city=port_moresby)

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_initial_data, migrations.RunPython.noop),
    ]
