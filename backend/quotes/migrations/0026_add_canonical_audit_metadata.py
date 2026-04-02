from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0025_quote_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="quoteline",
            name="basis",
            field=models.CharField(blank=True, help_text="Persisted canonical quote_result basis label.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="calculation_notes",
            field=models.TextField(blank=True, help_text="Persisted canonical line-level audit notes.", null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="canonical_cost_source",
            field=models.CharField(blank=True, help_text="Persisted canonical quote_result cost source.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="component",
            field=models.CharField(blank=True, help_text="Persisted canonical quote_result component.", max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="is_manual_override",
            field=models.BooleanField(blank=True, help_text="Persisted canonical manual-override flag.", null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="is_spot_sourced",
            field=models.BooleanField(blank=True, help_text="Persisted canonical SPOT-source flag.", null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="product_code",
            field=models.CharField(blank=True, help_text="Persisted canonical product code used in quote_result.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="rate",
            field=models.DecimalField(blank=True, decimal_places=6, help_text="Persisted canonical line rate when a stable rate is available.", max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="rate_source",
            field=models.CharField(blank=True, help_text="Persisted canonical quote_result rate source.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="rule_family",
            field=models.CharField(blank=True, help_text="Persisted canonical pricing calculation family.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="service_family",
            field=models.CharField(blank=True, help_text="Optional semantic/commercial family kept separate from rule_family.", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="quoteline",
            name="unit_type",
            field=models.CharField(blank=True, help_text="Persisted canonical quote_result unit type.", max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="quotetotal",
            name="audit_metadata_json",
            field=models.JSONField(blank=True, default=dict, help_text="Persisted structured audit metadata for quote_result."),
        ),
        migrations.AddField(
            model_name="quotetotal",
            name="customer_notes",
            field=models.TextField(blank=True, help_text="Persisted canonical customer-facing notes.", null=True),
        ),
        migrations.AddField(
            model_name="quotetotal",
            name="internal_notes",
            field=models.TextField(blank=True, help_text="Persisted canonical internal notes.", null=True),
        ),
        migrations.AddField(
            model_name="quotetotal",
            name="service_notes",
            field=models.TextField(blank=True, help_text="Persisted canonical service-facing notes.", null=True),
        ),
        migrations.AddField(
            model_name="quotetotal",
            name="warnings_json",
            field=models.JSONField(blank=True, default=list, help_text="Persisted canonical quote_result warnings."),
        ),
    ]
