# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Providers(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True)
    provider_type = models.TextField()

    class Meta:
        managed = True
        db_table = 'providers'


class Stations(models.Model):
    id = models.BigAutoField(primary_key=True)
    iata = models.TextField(unique=True)
    city = models.TextField(blank=True, null=True)
    country = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'stations'


class Ratecards(models.Model):
    id = models.BigAutoField(primary_key=True)
    provider = models.ForeignKey(Providers, on_delete=models.PROTECT)
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
        managed = True
        db_table = 'ratecards'
        unique_together = (('provider', 'name', 'effective_date'),)


class RatecardConfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.OneToOneField(Ratecards, on_delete=models.CASCADE)
    dim_factor_kg_per_m3 = models.DecimalField(max_digits=8, decimal_places=2)
    rate_strategy = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = True
        db_table = 'ratecard_config'


class Lanes(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey(Ratecards, on_delete=models.CASCADE)
    origin = models.ForeignKey(Stations, on_delete=models.PROTECT)
    dest = models.ForeignKey(Stations, on_delete=models.PROTECT, related_name='lanes_dest_set')
    via = models.ForeignKey(
        Stations,
        on_delete=models.SET_NULL,
        related_name='lanes_via_set',
        blank=True,
        null=True,
    )
    airline = models.TextField(blank=True, null=True)
    is_direct = models.BooleanField()

    # A unique constraint could not be introspected.
    class Meta:
        managed = True
        db_table = 'lanes'
        unique_together = (('ratecard', 'origin', 'dest'),)


class LaneBreaks(models.Model):
    id = models.BigAutoField(primary_key=True)
    lane = models.ForeignKey(Lanes, on_delete=models.CASCADE)
    break_code = models.TextField()
    per_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'lane_breaks'
        unique_together = (('lane', 'break_code'),)


class FeeTypes(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.TextField(unique=True)
    description = models.TextField()
    basis = models.TextField()
    default_tax_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        managed = True
        db_table = 'fee_types'


class RatecardFees(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey(Ratecards, on_delete=models.CASCADE)
    fee_type = models.ForeignKey(FeeTypes, on_delete=models.PROTECT)
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
        managed = True
        db_table = 'ratecard_fees'


class CartageLadders(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey(Ratecards, on_delete=models.CASCADE)
    min_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    max_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    rate_per_kg = models.DecimalField(max_digits=12, decimal_places=4)
    min_charge = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'cartage_ladders'
        unique_together = (('ratecard', 'min_weight_kg', 'max_weight_kg'),)


class StorageTiers(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey(Ratecards, on_delete=models.CASCADE)
    group_code = models.TextField()
    week_from = models.SmallIntegerField()
    week_to = models.SmallIntegerField()
    rate_per_kg_per_week = models.DecimalField(max_digits=12, decimal_places=4)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'storage_tiers'


class Services(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.TextField(unique=True)
    name = models.TextField()
    basis = models.TextField()

    class Meta:
        managed = True
        db_table = 'services'


class ServiceItems(models.Model):
    id = models.BigAutoField(primary_key=True)
    ratecard = models.ForeignKey(Ratecards, on_delete=models.CASCADE)
    service = models.ForeignKey(Services, on_delete=models.PROTECT)
    currency = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    percent_of_service_code = models.TextField(blank=True, null=True)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2)
    item_code = models.TextField(blank=True, null=True)
    conditions_json = models.JSONField()

    class Meta:
        managed = True
        db_table = 'service_items'


class SellCostLinksSimple(models.Model):
    id = models.BigAutoField(primary_key=True)
    sell_item = models.ForeignKey(ServiceItems, on_delete=models.CASCADE)
    buy_fee_code = models.ForeignKey(
        FeeTypes,
        on_delete=models.PROTECT,
        db_column='buy_fee_code',
        to_field='code',
    )
    mapping_type = models.TextField()
    mapping_value = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'sell_cost_links_simple'


class CurrencyRates(models.Model):
    id = models.BigAutoField(primary_key=True)
    as_of_ts = models.DateTimeField()
    base_ccy = models.TextField()
    quote_ccy = models.TextField()
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    # Distinguishes between TT 'BUY' and 'SELL' rates
    rate_type = models.CharField(max_length=8, default='BUY', help_text="Distinguishes between TT 'BUY' and 'SELL' rates.")
    source = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'currency_rates'
        unique_together = (('as_of_ts', 'base_ccy', 'quote_ccy', 'rate_type'),)


class PricingPolicy(models.Model):
    id = models.BigAutoField(primary_key=True)
    audience = models.TextField(unique=True)
    caf_on_fx = models.BooleanField()
    gst_applies = models.BooleanField()
    gst_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        managed = True
        db_table = 'pricing_policy'


class Organizations(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True)
    # Add this field to drive currency logic
    country_code = models.CharField(max_length=2, default='PG')  # e.g., PG, AU, US
    audience = models.TextField()
    default_sell_currency = models.TextField()
    gst_pct = models.DecimalField(max_digits=5, decimal_places=2)
    disbursement_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    disbursement_cap = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'organizations'


class Contacts(models.Model):
    id = models.BigAutoField(primary_key=True)
    org = models.ForeignKey(Organizations, on_delete=models.CASCADE)
    name = models.TextField()
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'contacts'


class Sites(models.Model):
    id = models.BigAutoField(primary_key=True)
    org = models.ForeignKey(Organizations, on_delete=models.CASCADE)
    label = models.TextField()
    address = models.TextField()
    city = models.TextField(blank=True, null=True)
    province = models.TextField(blank=True, null=True)
    country = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'sites'


class Quotes(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(Organizations, models.PROTECT)
    status = models.CharField(max_length=32, default='COMPLETE', help_text="e.g., COMPLETE, PENDING_RATE, EXPIRED")
    # Store the original request payload for reference
    request_snapshot = models.JSONField()
    # Store the calculated totals
    buy_total = models.DecimalField(max_digits=14, decimal_places=2)
    sell_total = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    # New: Selected Incoterm for this quote (e.g., DAP, EXW)
    incoterm = models.CharField(max_length=16, blank=True, null=True, help_text="e.g., DAP, EXW")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'quotes'
        verbose_name_plural = 'Quotes'


class QuoteLines(models.Model):
    id = models.BigAutoField(primary_key=True)
    quote = models.ForeignKey(Quotes, models.CASCADE, related_name='lines')
    code = models.CharField(max_length=64)
    description = models.TextField()
    is_buy = models.BooleanField()
    is_sell = models.BooleanField()
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=16)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    extended_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    # Add a field to flag lines that need manual input
    manual_rate_required = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'quote_lines'
        ordering = ['id']

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
        managed = True
        db_table = 'routes'
        verbose_name_plural = "Routes"


class RouteLegs(models.Model):
    id = models.BigAutoField(primary_key=True)
    route = models.ForeignKey(Routes, models.CASCADE, related_name="legs")
    sequence = models.PositiveIntegerField(help_text="Order of the leg in the journey, e.g., 1, 2, 3...")
    origin = models.ForeignKey(Stations, models.PROTECT, related_name='+')
    dest = models.ForeignKey(Stations, models.PROTECT, related_name='+')
    
    # Use this to find the correct BUY rate card (e.g., INTERNATIONAL, DOMESTIC)
    leg_scope = models.CharField(max_length=32, default='INTERNATIONAL')
    
    # Use this to determine the type of service and find appropriate SELL fees
    service_type = models.CharField(max_length=32, default='LINEHAUL', help_text="e.g., LINEHAUL, CLEARANCE, ONFORWARDING")

    def __str__(self):
        return f"{self.route.name} - Leg {self.sequence}: {self.origin.iata} to {self.dest.iata}"

    class Meta:
        managed = True
        db_table = 'route_legs'
        ordering = ['route', 'sequence']
