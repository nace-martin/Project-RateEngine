from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0034_spechargelinedb_conditional_acknowledgement"),
    ]

    operations = [
        migrations.AddField(
            model_name="spechargelinedb",
            name="source_excerpt",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Verbatim source snippet supporting this extracted charge line.",
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="source_line_number",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="One-based source line number for the supporting source excerpt, when available.",
                null=True,
            ),
        ),
    ]
