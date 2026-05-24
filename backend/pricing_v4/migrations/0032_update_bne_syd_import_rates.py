from decimal import Decimal
from datetime import date
from django.db import migrations


def update_bne_syd_rates(apps, schema_editor):
    ImportCOGS = apps.get_model('pricing_v4', 'ImportCOGS')
    ProductCode = apps.get_model('pricing_v4', 'ProductCode')

    def _reset_pricing_fields(obj):
        obj.rate_per_kg = None
        obj.rate_per_shipment = None
        obj.min_charge = None
        obj.max_charge = None
        obj.percent_rate = None
        obj.weight_breaks = None
        obj.is_additive = False

    # Helper function to safely update existing COGS rows.
    # Existing rows keep their counterparty; this migration only corrects the
    # rate card and scope structure for existing ProductCodes.
    def update_existing_cogs(
        product_code_code,
        origin_airport,
        destination_airport,
        scope,
        currency,
        defaults
    ):
        try:
            pc = ProductCode.objects.get(code=product_code_code)
        except ProductCode.DoesNotExist:
            print(f"ProductCode {product_code_code} not found, skipping.")
            return

        qs = ImportCOGS.objects.filter(
            product_code=pc,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            currency=currency,
        )
        if destination_airport is None:
            qs = ImportCOGS.objects.filter(
                product_code=pc,
                origin_airport=origin_airport,
                currency=currency,
            )

        for obj in qs:
            _reset_pricing_fields(obj)
            for field, value in defaults.items():
                setattr(obj, field, value)
            if scope:
                obj.scope = scope
            obj.currency = currency
            obj.destination_airport = destination_airport
            obj.save()

    # 1. FREIGHT CHARGES (BNE -> POM & SYD -> POM)
    # BNE -> POM IMP-FRT-AIR
    bne_frt_breaks = [
        {"min_kg": 0, "rate": "7.50"},
        {"min_kg": 45, "rate": "7.35"},
        {"min_kg": 100, "rate": "7.00"},
        {"min_kg": 250, "rate": "6.75"},
        {"min_kg": 500, "rate": "6.45"},
        {"min_kg": 1000, "rate": "6.10"},
    ]
    update_existing_cogs(
        product_code_code='IMP-FRT-AIR',
        origin_airport='BNE',
        destination_airport='POM',
        scope='LANE',
        currency='AUD',
        defaults={
            'rate_per_kg': None,
            'rate_per_shipment': None,
            'min_charge': Decimal('350.00'),
            'weight_breaks': bne_frt_breaks,
            'percent_rate': None,
            'valid_from': date(2025, 1, 1),
            'valid_until': date(2026, 12, 31),
        }
    )

    # SYD -> POM IMP-FRT-AIR
    syd_frt_breaks = [
        {"min_kg": 45, "rate": "8.10"},
        {"min_kg": 100, "rate": "7.55"},
        {"min_kg": 250, "rate": "7.50"},
        {"min_kg": 500, "rate": "7.20"},
        {"min_kg": 1000, "rate": "6.85"},
    ]
    update_existing_cogs(
        product_code_code='IMP-FRT-AIR',
        origin_airport='SYD',
        destination_airport='POM',
        scope='LANE',
        currency='AUD',
        defaults={
            'rate_per_kg': None,
            'rate_per_shipment': None,
            'min_charge': Decimal('415.00'),
            'weight_breaks': syd_frt_breaks,
            'percent_rate': None,
            'valid_from': date(2025, 1, 1),
            'valid_until': date(2026, 12, 31),
        }
    )

    # 2. ORIGIN LOCAL CHARGES (BNE & SYD, destination_airport=None)
    origins = ['BNE', 'SYD']
    for org in origins:
        # Pick Up: min 85.00, 0.26/kg
        update_existing_cogs(
            product_code_code='IMP-PICKUP',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'min_charge': Decimal('85.00'),
                'rate_per_kg': Decimal('0.26'),
                'rate_per_shipment': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # FSC Pick Up: 20%
        update_existing_cogs(
            product_code_code='IMP-FSC-PICKUP',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'percent_rate': Decimal('20.00'),
                'rate_per_kg': None,
                'rate_per_shipment': None,
                'min_charge': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # X-Ray Screening: min 70.00, 0.382/kg
        update_existing_cogs(
            product_code_code='IMP-SCREEN-ORIGIN',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'min_charge': Decimal('70.00'),
                'rate_per_kg': Decimal('0.382'),
                'rate_per_shipment': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # CTO Fee: 30.00 flat
        update_existing_cogs(
            product_code_code='IMP-CTO-ORIGIN',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'rate_per_shipment': Decimal('30.00'),
                'rate_per_kg': None,
                'min_charge': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # Export Document Fee: 82.00 flat
        update_existing_cogs(
            product_code_code='IMP-DOC-ORIGIN',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'rate_per_shipment': Decimal('82.00'),
                'rate_per_kg': None,
                'min_charge': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # Export Agency Fee: 175.00 flat
        update_existing_cogs(
            product_code_code='IMP-AGENCY-ORIGIN',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'rate_per_shipment': Decimal('175.00'),
                'rate_per_kg': None,
                'min_charge': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        # Origin AWB Fee: 30.00 flat
        update_existing_cogs(
            product_code_code='IMP-AWB-ORIGIN',
            origin_airport=org,
            destination_airport=None,
            scope='ORIGIN',
            currency='AUD',
            defaults={
                'rate_per_shipment': Decimal('30.00'),
                'rate_per_kg': None,
                'min_charge': None,
                'percent_rate': None,
                'weight_breaks': None,
                'valid_from': date(2025, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )


def rollback_bne_syd_rates(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0031_seed_bne_origin_local_cogs'),
    ]

    operations = [
        migrations.RunPython(update_bne_syd_rates, rollback_bne_syd_rates),
    ]
