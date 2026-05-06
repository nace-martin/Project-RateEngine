from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="opportunity",
            name="service_type",
            field=models.CharField(
                choices=[
                    ("AIR", "Air"),
                    ("SEA", "Sea"),
                    ("CUSTOMS", "Customs"),
                    ("TRANSPORT", "Transport"),
                    ("DOMESTIC", "Domestic"),
                    ("MULTIMODAL", "Multimodal"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
