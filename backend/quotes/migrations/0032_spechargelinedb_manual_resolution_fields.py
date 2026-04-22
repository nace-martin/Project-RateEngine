from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricing_v4", "0023_chargealias"),
        ("quotes", "0031_spechargelinedb_matched_alias_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="spechargelinedb",
            name="manual_resolution_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when manual SPOT charge review was saved.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="manual_resolution_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who manually reviewed or resolved this charge line.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="manual_resolution_status",
            field=models.CharField(
                blank=True,
                choices=[("RESOLVED", "Resolved")],
                db_index=True,
                help_text="Manual review outcome recorded without altering deterministic normalization audit fields.",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="spechargelinedb",
            name="manual_resolved_product_code",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical ProductCode selected during manual SPOT charge review.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="spe_manual_resolved_charge_lines",
                to="pricing_v4.productcode",
            ),
        ),
    ]
