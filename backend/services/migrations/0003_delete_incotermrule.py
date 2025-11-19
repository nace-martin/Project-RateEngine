from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0002_servicerule_servicerulecomponent_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="IncotermRule",
        ),
    ]
