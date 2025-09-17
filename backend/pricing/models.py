from django.db import models


class Ratecards(models.Model):
    id = models.BigAutoField(primary_key=True)
    provider = models.ForeignKey('core.Providers', models.DO_NOTHING)
    name = models.TextField()
    role = models.TextField()
    scope = models.TextField()
    direction = models.TextField()
    audience = models.TextField(blank=True, null=True)
    # Commodity code for the ratecard (e.g., GCR, DGR, LAR, PER)
    commodity_code = models.CharField(
        max_length=8,
        default='GCR',
        help_text="e.g., GCR, DGR, LAR, PER"
    )
    # New field to specify pricing strategy for this ratecard
    rate_strategy = models.CharField(max_length=32, null=True, blank=True, default="BREAKS")
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
        db_table = 'ratecards'
        unique_together = (('provider', 'name', 'effective_date'),)


class RatecardConfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.OneToOneField('pricing.Ratecards', models.DO_NOTHING)
    dim_factor_kg_per_m3 = models.DecimalField(max_digits=8, decimal_places=2)
    rate_strategy = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'ratecard_config'


class Lanes(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey('pricing.Ratecards', models.DO_NOTHING)
    origin = models.ForeignKey('core.Stations', models.DO_NOTHING)
    dest = models.ForeignKey('core.Stations', models.DO_NOTHING, related_name='lanes_dest_set')
    via = models.ForeignKey('core.Stations', models.DO_NOTHING, related_name='lanes_via_set', blank=True, null=True)
    airline = models.TextField(blank=True, null=True)
    is_direct = models.BooleanField()

    # A unique constraint could not be introspected.
    class Meta:
        db_table = 'lanes'
        unique_together = (('ratecard', 'origin', 'dest'),)


class LaneBreaks(models.Model):
    id = models.BigAutoField(primary_key=True)
    lane = models.ForeignKey('pricing.Lanes', models.DO_NOTHING)
    break_code = models.TextField()
    per_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = 'lane_breaks'
        unique_together = (('lane', 'break_code'),)


class RatecardFees(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey('pricing.Ratecards', models.DO_NOTHING)
    fee_type = models.ForeignKey('core.FeeTypes', models.DO_NOTHING)
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
        db_table = 'ratecard_fees'


class CartageLadders(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey('pricing.Ratecards', models.DO_NOTHING)
    min_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    max_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    rate_per_kg = models.DecimalField(max_digits=12, decimal_places=4)
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = 'cartage_ladders'
        unique_together = (('ratecard', 'min_weight_kg', 'max_weight_kg'),)


class StorageTiers(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey('pricing.Ratecards', models.DO_NOTHING)
    group_code = models.TextField()
    week_from = models.SmallIntegerField()
    week_to = models.SmallIntegerField()
    rate_per_kg_per_week = models.DecimalField(max_digits=12, decimal_places=4)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'storage_tiers'


class ServiceItems(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey('pricing.Ratecards', models.DO_NOTHING)
    service = models.ForeignKey('core.Services', models.DO_NOTHING)
    currency = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    percent_of_service_code = models.TextField(blank=True, null=True)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2)
    item_code = models.TextField(blank=True, null=True)
    conditions_json = models.JSONField()

    class Meta:
        db_table = 'service_items'


class SellCostLinksSimple(models.Model):
    id = models.BigAutoField(primary_key=True)
    sell_item = models.ForeignKey('pricing.ServiceItems', models.DO_NOTHING)
    buy_fee_code = models.ForeignKey('core.FeeTypes', models.DO_NOTHING, db_column='buy_fee_code', to_field='code')
    mapping_type = models.TextField()
    mapping_value = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)

    class Meta:
        db_table = 'sell_cost_links_simple'


class PricingPolicy(models.Model):
    id = models.BigAutoField(primary_key=True)
    audience = models.TextField(unique=True)
    caf_on_fx = models.BooleanField()
    gst_applies = models.BooleanField()
    gst_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = 'pricing_policy'


# New models for multi-leg journeys
class Routes(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True, help_text="e.g., Australia East Coast to Lae")
    origin_country = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2 code, e.g., AU")
    dest_country = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2 code, e.g., PG")
    shipment_type = models.CharField(max_length=16, choices=[("IMPORT", "Import"), ("EXPORT", "Export"), ("DOMESTIC", "Domestic")])
    # If true, quotes on this route require manual rate sourcing
    requires_manual_rate = models.BooleanField(
        default=False,
        help_text="If true, trigger manual rate request for all quotes on this route."
    )

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'routes'
        verbose_name_plural = "Routes"


class RouteLegs(models.Model):
    id = models.BigAutoField(primary_key=True)
    route = models.ForeignKey('pricing.Routes', models.CASCADE, related_name='legs')
    sequence = models.PositiveIntegerField(help_text="Order of the leg in the journey, e.g., 1, 2, 3...")
    origin = models.ForeignKey('core.Stations', models.PROTECT, related_name='+')
    dest = models.ForeignKey('core.Stations', models.PROTECT, related_name='+')

    # Use this to find the correct BUY rate card (e.g., INTERNATIONAL, DOMESTIC)
    leg_scope = models.CharField(max_length=32, default='INTERNATIONAL')

    # Use this to determine the type of service and find appropriate SELL fees
    service_type = models.CharField(max_length=32, default='LINEHAUL', help_text="e.g., LINEHAUL, CLEARANCE, ONFORWARDING")

    def __str__(self):
        return f"{self.route.name} - Leg {self.sequence}: {self.origin.iata} to {self.dest.iata}"

    class Meta:
        db_table = 'route_legs'
        ordering = ['route', 'sequence']

