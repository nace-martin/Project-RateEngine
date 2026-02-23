from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0018_quoteline_gst_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="spechargelinedb",
            name="calculation_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("flat", "Flat"),
                    ("per_unit", "Per Unit"),
                    ("min_or_per_unit", "Min Or Per Unit"),
                    ("percent_of", "Percent Of Basis"),
                    ("per_line_with_cap", "Per Line With Cap"),
                    ("max_or_per_unit", "Max Or Per Unit"),
                ],
                help_text="Rule type for canonical evaluation",
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="max_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Maximum amount for composite rules",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="min_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Minimum amount for composite rules",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Percent value for percentage rules",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="percent_basis",
            field=models.CharField(
                blank=True,
                help_text="Basis key for percentage calculation (e.g., 'freight')",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Per-unit or flat rate in charge currency",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="rule_meta",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Extensible rule params (e.g., cap thresholds)",
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="unit_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("kg", "Kilogram"),
                    ("shipment", "Shipment"),
                    ("awb", "AWB"),
                    ("trip", "Trip"),
                    ("set", "Set"),
                    ("line", "Line"),
                    ("man", "Man"),
                    ("cbm", "CBM"),
                    ("rt", "Revenue Ton"),
                ],
                help_text="Quantity basis for PER_UNIT style calculations",
                max_length=20,
                null=True,
            ),
        ),
    ]
