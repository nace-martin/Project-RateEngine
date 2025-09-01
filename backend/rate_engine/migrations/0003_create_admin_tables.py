from django.db import migrations, models


def create_admin_tables(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())

    # Define temp models reflecting db_table + fields exactly as in models.py
    class Providers(models.Model):
        id = models.BigAutoField(primary_key=True)
        name = models.TextField(unique=True)
        provider_type = models.TextField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'providers'

    class Stations(models.Model):
        id = models.BigAutoField(primary_key=True)
        iata = models.TextField(unique=True)
        city = models.TextField(blank=True, null=True)
        country = models.TextField(blank=True, null=True)

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'stations'

    class Ratecards(models.Model):
        id = models.BigAutoField(primary_key=True)
        provider = models.ForeignKey(Providers, models.DO_NOTHING)
        name = models.TextField()
        role = models.TextField()
        scope = models.TextField()
        direction = models.TextField()
        audience = models.TextField(blank=True, null=True)
        currency = models.TextField()
        source = models.TextField()
        status = models.TextField()
        effective_date = models.DateField()
        expiry_date = models.DateField(blank=True, null=True)
        notes = models.TextField(blank=True, null=True)
        meta = models.JSONField()
        created_at = models.DateTimeField()
        updated_at = models.DateTimeField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'ratecards'
            unique_together = (('provider', 'name', 'effective_date'),)

    class Services(models.Model):
        id = models.BigAutoField(primary_key=True)
        code = models.TextField(unique=True)
        name = models.TextField()
        basis = models.TextField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'services'

    class FeeTypes(models.Model):
        id = models.BigAutoField(primary_key=True)
        code = models.TextField(unique=True)
        description = models.TextField()
        basis = models.TextField()
        default_tax_pct = models.DecimalField(max_digits=5, decimal_places=2)

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'fee_types'

    class PricingPolicy(models.Model):
        id = models.BigAutoField(primary_key=True)
        audience = models.TextField(unique=True)
        caf_on_fx = models.BooleanField()
        gst_applies = models.BooleanField()
        gst_pct = models.DecimalField(max_digits=5, decimal_places=2)

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'pricing_policy'

    class RatecardConfig(models.Model):
        id = models.BigAutoField(primary_key=True)
        ratecard = models.OneToOneField(Ratecards, models.DO_NOTHING)
        dim_factor_kg_per_m3 = models.DecimalField(max_digits=8, decimal_places=2)
        rate_strategy = models.TextField()
        created_at = models.DateTimeField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'ratecard_config'

    class Lanes(models.Model):
        id = models.BigAutoField(primary_key=True)
        ratecard = models.ForeignKey(Ratecards, models.DO_NOTHING)
        origin = models.ForeignKey(Stations, models.DO_NOTHING)
        dest = models.ForeignKey(Stations, models.DO_NOTHING, related_name='lanes_dest_set')
        via = models.ForeignKey(Stations, models.DO_NOTHING, related_name='lanes_via_set', blank=True, null=True)
        airline = models.TextField(blank=True, null=True)
        is_direct = models.BooleanField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'lanes'
            unique_together = (('ratecard', 'origin', 'dest'),)

    class LaneBreaks(models.Model):
        id = models.BigAutoField(primary_key=True)
        lane = models.ForeignKey(Lanes, models.DO_NOTHING)
        break_code = models.TextField()
        per_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
        min_charge = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'lane_breaks'
            unique_together = (('lane', 'break_code'),)

    class RatecardFees(models.Model):
        id = models.BigAutoField(primary_key=True)
        ratecard = models.ForeignKey(Ratecards, models.DO_NOTHING)
        fee_type = models.ForeignKey(FeeTypes, models.DO_NOTHING)
        currency = models.TextField()
        amount = models.DecimalField(max_digits=12, decimal_places=4)
        min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
        max_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
        percent_of_code = models.TextField(blank=True, null=True)
        per_kg_threshold = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
        applies_if = models.JSONField()
        notes = models.TextField(blank=True, null=True)
        created_at = models.DateTimeField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'ratecard_fees'

    class ServiceItems(models.Model):
        id = models.BigAutoField(primary_key=True)
        ratecard = models.ForeignKey(Ratecards, models.DO_NOTHING)
        service = models.ForeignKey(Services, models.DO_NOTHING)
        currency = models.TextField()
        amount = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
        min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
        max_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
        percent_of_service_code = models.TextField(blank=True, null=True)
        tax_pct = models.DecimalField(max_digits=5, decimal_places=2)
        item_code = models.TextField(blank=True, null=True)
        conditions_json = models.JSONField()

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'service_items'

    class SellCostLinksSimple(models.Model):
        id = models.BigAutoField(primary_key=True)
        sell_item = models.ForeignKey(ServiceItems, models.DO_NOTHING)
        buy_fee_code = models.ForeignKey(
            FeeTypes,
            models.DO_NOTHING,
            db_column='buy_fee_code',
            to_field='code',
        )
        mapping_type = models.TextField()
        mapping_value = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)

        class Meta:
            app_label = 'rate_engine_mig'
            db_table = 'sell_cost_links_simple'

    # Creation order based on FK dependencies
    ordered_models = [
        (Providers, 'providers'),
        (Stations, 'stations'),
        (Ratecards, 'ratecards'),
        (Services, 'services'),
        (FeeTypes, 'fee_types'),
        (PricingPolicy, 'pricing_policy'),
        (RatecardConfig, 'ratecard_config'),
        (Lanes, 'lanes'),
        (LaneBreaks, 'lane_breaks'),
        (RatecardFees, 'ratecard_fees'),
        (ServiceItems, 'service_items'),
        (SellCostLinksSimple, 'sell_cost_links_simple'),
    ]

    for ModelCls, table in ordered_models:
        if table not in existing:
            schema_editor.create_model(ModelCls)


class Migration(migrations.Migration):
    dependencies = [
        ('rate_engine', '0002_create_currency_rates'),
    ]

    operations = [
        migrations.RunPython(create_admin_tables, migrations.RunPython.noop),
    ]
