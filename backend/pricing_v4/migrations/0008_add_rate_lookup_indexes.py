# pricing_v4/migrations/0008_add_rate_lookup_indexes.py
# Generated manually for database optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0007_add_surcharge_filters_and_domestic_weight_breaks'),
    ]

    operations = [
        # Export COGS: lane + product lookup
        migrations.AddIndex(
            model_name='exportcogs',
            index=models.Index(
                fields=['origin_airport', 'destination_airport', 'product_code'],
                name='export_cogs_lane_product_idx'
            ),
        ),
        # Export Sell: lane + product lookup
        migrations.AddIndex(
            model_name='exportsellrate',
            index=models.Index(
                fields=['origin_airport', 'destination_airport', 'product_code'],
                name='export_sell_lane_product_idx'
            ),
        ),
        # Import COGS: lane + product lookup
        migrations.AddIndex(
            model_name='importcogs',
            index=models.Index(
                fields=['origin_airport', 'destination_airport', 'product_code'],
                name='import_cogs_lane_product_idx'
            ),
        ),
        # Import Sell: lane + product lookup
        migrations.AddIndex(
            model_name='importsellrate',
            index=models.Index(
                fields=['origin_airport', 'destination_airport', 'product_code'],
                name='import_sell_lane_product_idx'
            ),
        ),
        # Domestic COGS: zone + product lookup
        migrations.AddIndex(
            model_name='domesticcogs',
            index=models.Index(
                fields=['origin_zone', 'destination_zone', 'product_code'],
                name='domestic_cogs_zone_product_idx'
            ),
        ),
        # Domestic Sell: zone + product lookup
        migrations.AddIndex(
            model_name='domesticsellrate',
            index=models.Index(
                fields=['origin_zone', 'destination_zone', 'product_code'],
                name='domestic_sell_zone_product_idx'
            ),
        ),
        # Surcharge: service type + rate side lookup
        migrations.AddIndex(
            model_name='surcharge',
            index=models.Index(
                fields=['service_type', 'rate_side', 'product_code'],
                name='surcharge_type_side_product_idx'
            ),
        ),
    ]
