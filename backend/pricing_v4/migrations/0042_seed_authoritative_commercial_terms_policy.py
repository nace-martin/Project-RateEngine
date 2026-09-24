# Generated manually for Wave 3B2: Clean Database Architecture v2.1

import datetime
from decimal import Decimal

from django.db import migrations


def seed_commercial_terms_policy(apps, schema_editor):
    CommercialTermsPolicy = apps.get_model('pricing_v4', 'CommercialTermsPolicy')

    # Canonical Launch Commercial Terms Policy
    CommercialTermsPolicy.objects.get_or_create(
        policy_code="LAUNCH-POLICY-2026",
        defaults={
            "valid_from": datetime.date(2026, 1, 1),
            "valid_until": None,
            "target_gross_margin_percent": Decimal("20.00"),
            "import_caf_percent": Decimal("5.00"),
            "export_caf_percent": Decimal("10.00"),
            "gst_standard_percent": Decimal("10.00"),
            "is_active": True,
        }
    )


def reverse_seed_commercial_terms_policy(apps, schema_editor):
    CommercialTermsPolicy = apps.get_model('pricing_v4', 'CommercialTermsPolicy')
    CommercialTermsPolicy.objects.filter(policy_code="LAUNCH-POLICY-2026").delete()


class Migration(migrations.Migration):

    dependencies = [  # noqa: RUF012
        ('pricing_v4', '0041_drop_orphaned_pricing_v3_tables'),
    ]

    operations = [  # noqa: RUF012
        migrations.RunPython(seed_commercial_terms_policy, reverse_seed_commercial_terms_policy),
    ]
