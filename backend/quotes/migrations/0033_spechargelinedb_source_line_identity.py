from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0032_spechargelinedb_manual_resolution_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="spechargelinedb",
            name="source_line_identity",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Stable reconciliation key for imported source lines, using extractor identity or a structural fallback fingerprint.",
                max_length=255,
            ),
        ),
    ]
