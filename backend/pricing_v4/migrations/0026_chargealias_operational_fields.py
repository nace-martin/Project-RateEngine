from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricing_v4", "0025_alter_productcode_category_regulatory"),
    ]

    operations = [
        migrations.AddField(
            model_name="chargealias",
            name="alias_source",
            field=models.CharField(
                choices=[
                    ("SEED", "Seed / Bootstrap"),
                    ("ADMIN", "Admin Managed"),
                    ("MANUAL_REVIEW", "Manual Review Candidate"),
                ],
                db_index=True,
                default="ADMIN",
                help_text="Operational provenance for how this alias entered the registry.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="chargealias",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("APPROVED", "Approved"),
                    ("CANDIDATE", "Candidate"),
                    ("REJECTED", "Rejected"),
                ],
                db_index=True,
                default="APPROVED",
                help_text="Human review state. Only APPROVED aliases may be active.",
                max_length=20,
            ),
        ),
    ]
