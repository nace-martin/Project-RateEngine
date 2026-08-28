from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0048_restore_quoteline_preservation_columns"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="quote",
            name="opportunity",
        ),
    ]
