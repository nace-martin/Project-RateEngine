from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_delete_aircrafttype_routelaneconstraint_surcharge"),
    ]

    operations = [
        migrations.DeleteModel(
            name="FxRate",
        ),
    ]
