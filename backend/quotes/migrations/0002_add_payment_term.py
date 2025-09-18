# Generated manually for adding payment_term field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotes",
            name="payment_term",
            field=models.CharField(choices=[("PREPAID", "Prepaid"), ("COLLECT", "Collect")], default="PREPAID", max_length=16),
        ),
    ]
