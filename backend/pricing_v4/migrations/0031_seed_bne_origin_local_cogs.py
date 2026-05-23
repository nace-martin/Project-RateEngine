import uuid
from django.db import migrations


def seed_bne_origin_local_cogs(apps, schema_editor):
    ImportCOGS = apps.get_model('pricing_v4', 'ImportCOGS')
    
    # Query SYD origin-local charges where destination_airport is NULL or empty
    syd_rows = ImportCOGS.objects.filter(
        origin_airport='SYD',
        destination_airport__isnull=True,
        scope='ORIGIN'
    )
    
    # Also support empty string just in case
    if not syd_rows.exists():
        syd_rows = ImportCOGS.objects.filter(
            origin_airport='SYD',
            destination_airport='',
            scope='ORIGIN'
        )
        
    # Product codes we need to seed for BNE (since IMP-AGENCY-ORIGIN already exists)
    target_product_codes = {
        'IMP-DOC-ORIGIN',
        'IMP-AWB-ORIGIN',
        'IMP-CTO-ORIGIN',
        'IMP-SCREEN-ORIGIN',
        'IMP-PICKUP',
        'IMP-FSC-PICKUP'
    }
    
    for row in syd_rows:
        if row.product_code.code in target_product_codes:
            # Check if BNE row already exists to prevent duplicate seeding
            exists = ImportCOGS.objects.filter(
                origin_airport='BNE',
                destination_airport=row.destination_airport,
                product_code=row.product_code,
                agent=row.agent,
                carrier=row.carrier
            ).exists()
            
            if not exists:
                ImportCOGS.objects.create(
                    product_code=row.product_code,
                    origin_airport='BNE',
                    destination_airport=row.destination_airport,
                    scope=row.scope,
                    carrier=row.carrier,
                    agent=row.agent,
                    currency=row.currency,
                    rate_per_kg=row.rate_per_kg,
                    rate_per_shipment=row.rate_per_shipment,
                    min_charge=row.min_charge,
                    max_charge=row.max_charge,
                    is_additive=row.is_additive,
                    percent_rate=row.percent_rate,
                    weight_breaks=row.weight_breaks,
                    valid_from=row.valid_from,
                    valid_until=row.valid_until,
                    created_by=row.created_by,
                    updated_by=row.updated_by,
                    lineage_id=uuid.uuid4()
                )


def remove_bne_origin_local_cogs(apps, schema_editor):
    ImportCOGS = apps.get_model('pricing_v4', 'ImportCOGS')
    target_product_codes = {
        'IMP-DOC-ORIGIN',
        'IMP-AWB-ORIGIN',
        'IMP-CTO-ORIGIN',
        'IMP-SCREEN-ORIGIN',
        'IMP-PICKUP',
        'IMP-FSC-PICKUP'
    }
    ImportCOGS.objects.filter(
        origin_airport='BNE',
        destination_airport__isnull=True,
        product_code__code__in=target_product_codes
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0030_normalize_import_cogs_origin_phase_3b'),
    ]

    operations = [
        migrations.RunPython(seed_bne_origin_local_cogs, remove_bne_origin_local_cogs),
    ]
