from decimal import Decimal
from datetime import date
from django.db import migrations


def seed_export_fsc_rate(apps, schema_editor):
    ProductCode = apps.get_model('pricing_v4', 'ProductCode')
    LocalSellRate = apps.get_model('pricing_v4', 'LocalSellRate')

    # Ensure EXP-FSC-AIR ProductCode exists
    pc, created = ProductCode.objects.get_or_create(
        id=1002,
        defaults={
            'code': 'EXP-FSC-AIR',
            'description': 'Airline Export Fuel Surcharge',
            'domain': 'EXPORT',
            'category': 'SURCHARGE',
            'is_gst_applicable': True,
            'gst_rate': Decimal('0.1000'),
            'gst_treatment': 'STANDARD',
            'gl_revenue_code': '4000',
            'gl_cost_code': '5000',
            'default_unit': 'KG',
        }
    )

    # Seed the LocalSellRate row
    LocalSellRate.objects.update_or_create(
        product_code=pc,
        location='POM',
        direction='EXPORT',
        payment_term='ANY',
        currency='PGK',
        valid_from=date(2025, 1, 1),
        defaults={
            'rate_type': 'PER_KG',
            'amount': Decimal('0.8000'),
            'valid_until': date(2030, 12, 31),
            'scope': 'LOCAL',
        }
    )


def reverse_seed(apps, schema_editor):
    LocalSellRate = apps.get_model('pricing_v4', 'LocalSellRate')
    LocalSellRate.objects.filter(
        product_code_id=1002,
        location='POM',
        direction='EXPORT',
        payment_term='ANY',
        currency='PGK',
        valid_from=date(2025, 1, 1),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0030_normalize_import_cogs_origin_phase_3b'),
    ]

    operations = [
        migrations.RunPython(seed_export_fsc_rate, reverse_seed),
    ]
