from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0050_remove_quote_opportunity"),
    ]

    operations = [
        migrations.DeleteModel(name="RouteAutomationPolicyDB"),
    ]
