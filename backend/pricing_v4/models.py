# backend/pricing_v4/models.py
"""
Greenfield Pricing Engine Models - V4

Design Principles (Non-Negotiable Rules):
- Rule 1: No shared rate tables
- Rule 2: COGS and Sell never touch
- Rule 3: One ProductCode = One commercial truth
- Rule 4: Direction-specific definitions only
- Rule 6: Duplication > Ambiguity
- Rule 7: No magic flags
- Rule 8: ProductCode before rates (FK enforced)

Amendment: Carrier vs Agent distinction
- Carrier: Airlines/shipping lines (for freight linehaul COGS)
- Agent: Forwarders/partners (for origin/destination charges)
- A rate row must reference exactly ONE counterparty (carrier OR agent, never both)
"""

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from core.commodity import COMMODITY_CHOICES, DEFAULT_COMMODITY_CODE
from pricing_v4.category_rules import is_local_rate_category


# =============================================================================
# COUNTERPARTY ENTITIES: Carrier & Agent
# =============================================================================

class Carrier(models.Model):
    """
    Airlines and shipping lines that physically transport cargo.
    
    Examples: PX (Air Niugini), QF (Qantas), CZ (China Southern)
    
    Usage: Freight linehaul COGS only
    """
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    carrier_type = models.CharField(
        max_length=10,
        choices=[
            ('AIRLINE', 'Airline'),
            ('SHIPPING', 'Shipping Line'),
        ],
        default='AIRLINE',
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'carriers'
        ordering = ['code']
        verbose_name = 'Carrier'
        verbose_name_plural = 'Carriers'
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Agent(models.Model):
    """
    Freight forwarders and service partners.
    
    Examples: EFM AU (our Australia agent), destination agents, overseas forwarders
    
    Usage: Origin/destination charges, agency fees, pickup/delivery
    """
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2)  # ISO 2-letter
    
    # Agent type
    agent_type = models.CharField(
        max_length=20,
        choices=[
            ('ORIGIN', 'Origin Agent'),
            ('DESTINATION', 'Destination Agent'),
            ('BOTH', 'Origin & Destination'),
        ],
        default='BOTH',
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agents'
        ordering = ['code']
        verbose_name = 'Agent'
        verbose_name_plural = 'Agents'
    
    def __str__(self):
        return f"{self.code} - {self.name} ({self.country_code})"


# =============================================================================
# MASTER REGISTRY: ProductCode
# =============================================================================

class ProductCode(models.Model):
    """
    Master registry of all chargeable products/services.
    
    Rule 3: One ProductCode = One Commercial Truth
    Rule 8: ProductCode must exist before any rate row (FK enforced)
    
    ID Ranges (immutable, manually assigned):
    - 1xxx = Export
    - 2xxx = Import
    - 3xxx = Domestic
    """
    
    # Primary key: manually assigned, immutable
    id = models.IntegerField(primary_key=True)
    
    # Human-readable code (for debugging/display only, NOT for logic)
    code = models.CharField(max_length=30, unique=True, db_index=True)
    
    # Commercial identity
    description = models.CharField(max_length=200)
    
    # Domain - explicit, no flags
    DOMAIN_EXPORT = 'EXPORT'
    DOMAIN_IMPORT = 'IMPORT'
    DOMAIN_DOMESTIC = 'DOMESTIC'
    DOMAIN_CHOICES = [
        (DOMAIN_EXPORT, 'Export'),
        (DOMAIN_IMPORT, 'Import'),
        (DOMAIN_DOMESTIC, 'Domestic'),
    ]
    domain = models.CharField(max_length=10, choices=DOMAIN_CHOICES, db_index=True)
    
    # Category for grouping on quotes/invoices
    CATEGORY_FREIGHT = 'FREIGHT'
    CATEGORY_HANDLING = 'HANDLING'
    CATEGORY_CLEARANCE = 'CLEARANCE'
    CATEGORY_DOCUMENTATION = 'DOCUMENTATION'
    CATEGORY_CARTAGE = 'CARTAGE'
    CATEGORY_AGENCY = 'AGENCY'
    CATEGORY_SCREENING = 'SCREENING'
    CATEGORY_SURCHARGE = 'SURCHARGE'
    CATEGORY_CHOICES = [
        (CATEGORY_FREIGHT, 'Freight'),
        (CATEGORY_HANDLING, 'Handling & Terminal'),
        (CATEGORY_CLEARANCE, 'Customs Clearance'),
        (CATEGORY_DOCUMENTATION, 'Documentation'),
        (CATEGORY_CARTAGE, 'Pickup & Delivery'),
        (CATEGORY_AGENCY, 'Agency Fees'),
        (CATEGORY_SCREENING, 'Security & Screening'),
        (CATEGORY_SURCHARGE, 'Surcharges'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    
    # Tax configuration - explicit booleans, no magic
    is_gst_applicable = models.BooleanField()
    gst_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.10'))
    
    # GST Treatment Classification
    GST_TREATMENT_STANDARD = 'STANDARD'      # Normal 10% GST (tracked in BAS)
    GST_TREATMENT_ZERO_RATED = 'ZERO_RATED'  # Export - 0% but included in BAS return
    GST_TREATMENT_EXEMPT = 'EXEMPT'          # Disbursements - excluded from BAS entirely
    
    GST_TREATMENT_CHOICES = [
        (GST_TREATMENT_STANDARD, 'Standard (10% GST)'),
        (GST_TREATMENT_ZERO_RATED, 'Zero-Rated (Export)'),
        (GST_TREATMENT_EXEMPT, 'Exempt (Disbursement)'),
    ]
    
    gst_treatment = models.CharField(
        max_length=15,
        choices=GST_TREATMENT_CHOICES,
        default=GST_TREATMENT_STANDARD,
        db_index=True,
        help_text='STANDARD=10%, ZERO_RATED=0% (tracked), EXEMPT=0% (not tracked)'
    )
    
    # Accounting codes - explicit strings
    gl_revenue_code = models.CharField(max_length=20)
    gl_cost_code = models.CharField(max_length=20)
    
    # Unit basis
    UNIT_SHIPMENT = 'SHIPMENT'
    UNIT_KG = 'KG'
    UNIT_PERCENT = 'PERCENT'  # For percentage-based surcharges
    UNIT_CHOICES = [
        (UNIT_SHIPMENT, 'Per Shipment'),
        (UNIT_KG, 'Per Kilogram'),
        (UNIT_PERCENT, 'Percentage'),
    ]
    default_unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_SHIPMENT)
    
    # Percentage surcharge: reference to base ProductCode
    percent_of_product_code = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='dependent_surcharges',
        help_text='For PERCENT unit: the ProductCode this is a percentage of'
    )
    
    # Timestamps (no magic flags like is_active)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'product_codes'
        ordering = ['id']
        verbose_name = 'Product Code'
        verbose_name_plural = 'Product Codes'
    
    def __str__(self):
        return f"{self.id} - {self.code}: {self.description}"
    
    def clean(self):
        """Validate ID range matches domain."""
        if self.domain == self.DOMAIN_EXPORT and not (1000 <= self.id < 2000):
            raise ValidationError(f"Export ProductCode ID must be 1xxx, got {self.id}")
        elif self.domain == self.DOMAIN_IMPORT and not (2000 <= self.id < 3000):
            raise ValidationError(f"Import ProductCode ID must be 2xxx, got {self.id}")
        elif self.domain == self.DOMAIN_DOMESTIC and not (3000 <= self.id < 4000):
            raise ValidationError(f"Domestic ProductCode ID must be 3xxx, got {self.id}")


# =============================================================================
# EXPORT RATE TABLES
# =============================================================================

class ExportCOGS(models.Model):
    """
    What EFM PAYS for Export services (Cost of Goods Sold).
    
    Rule 1: Separate table for Export COGS
    Rule 2: COGS and Sell never touch
    Rule 8: ProductCode FK enforced
    
    Counterparty: EITHER carrier (for freight) OR agent (for services), never both
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='export_cogs_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_EXPORT}
    )
    
    # Lane definition - explicit IATA codes, no abstraction
    origin_airport = models.CharField(max_length=3, db_index=True)
    destination_airport = models.CharField(max_length=3, db_index=True)
    
    # Counterparty: carrier OR agent (never both, never null for both)
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='export_cogs_rates',
        help_text='For freight linehaul only'
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='export_cogs_rates',
        help_text='For origin/destination services'
    )
    
    # Rate values - all explicit, nullable where optional
    currency = models.CharField(max_length=3)  # PGK, AUD, USD
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag: if True, rate_per_kg + rate_per_shipment are ADDED together
    # (e.g., Security Screening: K0.17/kg + K35 flat)
    is_additive = models.BooleanField(default=False)
    
    # Weight break tiers - explicit JSON format
    # Format: [{"min_kg": 0, "rate": "6.30"}, {"min_kg": 100, "rate": "5.90"}, ...]
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity - explicit dates, required
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'export_cogs'
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Export COGS'
        verbose_name_plural = 'Export COGS'
        constraints = [
            # Ensure exactly one counterparty (carrier XOR agent)
            models.CheckConstraint(
                check=(
                    models.Q(carrier__isnull=False, agent__isnull=True) |
                    models.Q(carrier__isnull=True, agent__isnull=False)
                ),
                name='export_cogs_one_counterparty'
            ),
        ]
    
    def clean(self):
        """Validate exactly one counterparty is set."""
        if self.carrier and self.agent:
            raise ValidationError("Cannot set both carrier and agent. Choose one.")
        if not self.carrier and not self.agent:
            raise ValidationError("Must set either carrier or agent.")
        if self.product_code and is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is a local charge and must be stored in LocalCOGSRate, not ExportCOGS."
            )
    
    def __str__(self):
        counterparty = self.carrier or self.agent
        return f"COGS: {self.product_code.code} {self.origin_airport}→{self.destination_airport} ({counterparty})"


class ExportSellRate(models.Model):
    """
    What EFM CHARGES for Export services (Sell Rate).
    
    Rule 1: Separate table for Export Sell
    Rule 2: COGS and Sell never touch
    Rule 8: ProductCode FK enforced
    
    Note: Sell rates may be agent-agnostic (EFM internal rates)
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='export_sell_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_EXPORT}
    )
    
    # Lane definition
    origin_airport = models.CharField(max_length=3, db_index=True)
    destination_airport = models.CharField(max_length=3, db_index=True)
    
    # Rate values
    currency = models.CharField(max_length=3)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Percentage of another charge (for surcharges like FSC)
    percent_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Percentage rate (e.g., 10.00 for 10%)'
    )
    
    # Weight break tiers
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'export_sell_rates'
        unique_together = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'valid_from']
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Export Sell Rate'
        verbose_name_plural = 'Export Sell Rates'

    def clean(self):
        if self.product_code and is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is a local charge and must be stored in LocalSellRate, not ExportSellRate."
            )
    
    def __str__(self):
        return f"SELL: {self.product_code.code} {self.origin_airport}→{self.destination_airport}"


# =============================================================================
# IMPORT RATE TABLES
# =============================================================================

class ImportCOGS(models.Model):
    """
    What EFM PAYS for Import services (Cost of Goods Sold).
    
    Rule 1: Separate table for Import COGS
    Rule 4: Direction-specific only
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='import_cogs_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_IMPORT}
    )
    
    # Lane definition
    origin_airport = models.CharField(max_length=3, db_index=True)
    destination_airport = models.CharField(max_length=3, db_index=True)
    
    # Counterparty: carrier OR agent
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='import_cogs_rates',
        help_text='For freight linehaul only'
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='import_cogs_rates',
        help_text='For origin/destination services'
    )
    
    # Rate values
    currency = models.CharField(max_length=3)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Percentage rate for surcharges (e.g. 20% FSC)
    percent_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Percentage rate (e.g., 20.00 for 20%)'
    )
    
    # Weight break tiers
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'import_cogs'
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Import COGS'
        verbose_name_plural = 'Import COGS'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(carrier__isnull=False, agent__isnull=True) |
                    models.Q(carrier__isnull=True, agent__isnull=False)
                ),
                name='import_cogs_one_counterparty'
            ),
        ]
    
    def clean(self):
        """Validate exactly one counterparty is set."""
        if self.carrier and self.agent:
            raise ValidationError("Cannot set both carrier and agent. Choose one.")
        if not self.carrier and not self.agent:
            raise ValidationError("Must set either carrier or agent.")
        if self.product_code and is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is a local charge and must be stored in LocalCOGSRate, not ImportCOGS."
            )
    
    def __str__(self):
        counterparty = self.carrier or self.agent
        return f"COGS: {self.product_code.code} {self.origin_airport}→{self.destination_airport} ({counterparty})"


class ImportSellRate(models.Model):
    """
    What EFM CHARGES for Import services (Sell Rate).
    
    Rule 1: Separate table for Import Sell
    Rule 4: Direction-specific only
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='import_sell_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_IMPORT}
    )
    
    # Lane definition
    origin_airport = models.CharField(max_length=3, db_index=True)
    destination_airport = models.CharField(max_length=3, db_index=True)
    
    # Rate values
    currency = models.CharField(max_length=3)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Percentage rate for surcharges
    percent_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Percentage rate (e.g., 10.00 for 10%)'
    )
    
    # Weight break tiers
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'import_sell_rates'
        unique_together = ['product_code', 'origin_airport', 'destination_airport', 'currency', 'valid_from']
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Import Sell Rate'
        verbose_name_plural = 'Import Sell Rates'

    def clean(self):
        if self.product_code and is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is a local charge and must be stored in LocalSellRate, not ImportSellRate."
            )
    
    def __str__(self):
        return f"SELL: {self.product_code.code} {self.origin_airport}→{self.destination_airport}"


# =============================================================================
# DOMESTIC RATE TABLES
# =============================================================================

class DomesticCOGS(models.Model):
    """
    What EFM PAYS for Domestic services (Cost of Goods Sold).
    
    Rule 1: Separate table for Domestic COGS
    Rule 4: Direction-specific only
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='domestic_cogs_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_DOMESTIC}
    )
    
    # Zone definition (domestic uses zones, not airports)
    origin_zone = models.CharField(max_length=20, db_index=True)
    destination_zone = models.CharField(max_length=20, db_index=True)
    
    # Counterparty: carrier OR agent (never both)
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='domestic_cogs_rates',
        help_text='For freight linehaul (e.g. PX)'
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='domestic_cogs_rates',
        help_text='For local services (e.g. Cartage)'
    )
    
    # Rate values - domestic is always PGK
    currency = models.CharField(max_length=3, default='PGK')
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Weight break tiers (for tiered pricing)
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'domestic_cogs'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(carrier__isnull=False, agent__isnull=True) |
                    models.Q(carrier__isnull=True, agent__isnull=False)
                ),
                name='domestic_cogs_one_counterparty'
            )
        ]
        ordering = ['product_code', 'origin_zone', 'destination_zone']
        verbose_name = 'Domestic COGS'
        verbose_name_plural = 'Domestic COGS'
    
    def clean(self):
        if self.carrier and self.agent:
            raise ValidationError("Cannot set both carrier and agent.")
        if not self.carrier and not self.agent:
            raise ValidationError("Must set either carrier or agent.")

    def __str__(self):
        cp = self.carrier or self.agent
        return f"COGS: {self.product_code.code} {self.origin_zone}→{self.destination_zone} ({cp})"


class DomesticSellRate(models.Model):
    """
    What EFM CHARGES for Domestic services (Sell Rate).
    
    Rule 1: Separate table for Domestic Sell
    Rule 4: Direction-specific only
    """
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='domestic_sell_rates',
        limit_choices_to={'domain': ProductCode.DOMAIN_DOMESTIC}
    )
    
    # Zone definition
    origin_zone = models.CharField(max_length=20, db_index=True)
    destination_zone = models.CharField(max_length=20, db_index=True)
    
    # Rate values
    currency = models.CharField(max_length=3, default='PGK')
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Percentage rate for surcharges
    percent_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Percentage rate (e.g., 10.00 for 10%)'
    )
    
    # Weight break tiers (for tiered pricing)
    weight_breaks = models.JSONField(null=True, blank=True)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'domestic_sell_rates'
        unique_together = ['product_code', 'origin_zone', 'destination_zone', 'valid_from']
        ordering = ['product_code', 'origin_zone', 'destination_zone']
        verbose_name = 'Domestic Sell Rate'
        verbose_name_plural = 'Domestic Sell Rates'
    
    def __str__(self):
        return f"SELL: {self.product_code.code} {self.origin_zone}→{self.destination_zone}"


# =============================================================================
# GLOBAL SURCHARGES (Normalized Design)
# =============================================================================

class Surcharge(models.Model):
    """
    Global surcharges that apply to service types, not individual routes.
    
    Design Principle:
    - Store surcharges ONCE, apply to all routes of a service type
    - Avoids duplication across 25+ routes
    - Single point of update for rate changes
    
    Examples:
    - Documentation Fee: K35.00 flat (DOMESTIC_AIR)
    - Fuel Surcharge: K0.25/kg (DOMESTIC_AIR)
    """
    
    SERVICE_TYPE_CHOICES = [
        ('DOMESTIC_AIR', 'Domestic Air'),
        ('EXPORT_AIR', 'Export Air'),
        ('IMPORT_AIR', 'Import Air'),
        ('EXPORT_ORIGIN', 'Export Origin Services'),
        ('EXPORT_DEST', 'Export Destination Services'),
        ('IMPORT_ORIGIN', 'Import Origin Services'),
        ('IMPORT_DEST', 'Import Destination Services'),
        ('ALL', 'All Service Types'),
    ]
    
    RATE_TYPE_CHOICES = [
        ('FLAT', 'Fixed Per Shipment'),
        ('PER_KG', 'Per Kilogram'),
        ('PERCENT', 'Percentage'),
    ]
    
    RATE_SIDE_CHOICES = [
        ('COGS', 'Cost of Goods Sold'),
        ('SELL', 'Sell Rate'),
    ]
    
    # Link to ProductCode for consistency
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='surcharges',
        help_text='The ProductCode this surcharge represents'
    )
    
    # COGS or SELL
    rate_side = models.CharField(
        max_length=4,
        choices=RATE_SIDE_CHOICES,
        default='COGS',
        db_index=True
    )
    
    # Service type this surcharge applies to
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPE_CHOICES,
        db_index=True
    )
    
    # Rate definition
    rate_type = models.CharField(max_length=10, choices=RATE_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=4)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    currency = models.CharField(max_length=3, default='PGK')
    
    # Optional lane filters (NULL = apply to ALL lanes)
    origin_filter = models.CharField(
        max_length=3,
        null=True,
        blank=True,
        db_index=True,
        help_text='IATA code to restrict origin (NULL = all origins)'
    )
    destination_filter = models.CharField(
        max_length=3,
        null=True,
        blank=True,
        db_index=True,
        help_text='IATA code to restrict destination (NULL = all destinations)'
    )
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'surcharges'
        unique_together = ['product_code', 'service_type', 'rate_side', 'valid_from']
        ordering = ['service_type', 'product_code']
        verbose_name = 'Surcharge'
        verbose_name_plural = 'Surcharges'
    
    def __str__(self):
        return f"{self.product_code.code} ({self.service_type}): {self.amount} {self.rate_type}"


# =============================================================================
# COMPONENT MARGINS
# =============================================================================

class ComponentMargin(models.Model):
    """
    Standard margins applied to COGS to determine Sell Rate.
    
    Principles:
    - Margins are defined per Service Type (e.g. DOMESTIC_AIR) or specific ProductCode
    - Margins can be percentage-based or fixed amounts
    - Specific rules override general rules (Specific Product > Service Type)
    """
    
    SERVICE_TYPE_CHOICES = [
        ('DOMESTIC_AIR', 'Domestic Air'),
        ('EXPORT_AIR', 'Export Air'),
        ('IMPORT_AIR', 'Import Air'),
        ('EXPORT_ORIGIN', 'Export Origin Services'),
        ('EXPORT_DEST', 'Export Destination Services'),
        ('IMPORT_ORIGIN', 'Import Origin Services'),
        ('IMPORT_DEST', 'Import Destination Services'),
    ]
    
    MARGIN_TYPE_CHOICES = [
        ('PERCENT', 'Percentage Markup'),
        ('FIXED', 'Fixed Amount Markup'),
    ]
    
    # Scope: Either a specific ProductCode OR a whole Service Type
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='component_margins',
        help_text='Specific product margin (overrides service type margin)'
    )
    
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPE_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text='Apply to all products in this service group'
    )
    
    # Margin definition
    margin_type = models.CharField(max_length=10, choices=MARGIN_TYPE_CHOICES, default='PERCENT')
    margin_value = models.DecimalField(max_digits=10, decimal_places=4, help_text='Percentage (e.g. 20.0 for 20%) or Fixed Amount')
    
    min_margin_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text='Minimum margin amount in currency (e.g. maintain at least K10 profit)'
    )
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'component_margins'
        ordering = ['service_type', 'product_code']
        verbose_name = 'Component Margin'
        verbose_name_plural = 'Component Margins'
    
    def clean(self):
        if not self.product_code and not self.service_type:
            raise ValidationError("Must specify either Product Code or Service Type.")
        if self.product_code and self.service_type:
            raise ValidationError("Cannot specify both. Choose specific Product or general Service Type.")
            
    def __str__(self):
        scope = self.product_code.code if self.product_code else self.service_type
        return f"Margin: {scope} ({self.margin_value} {self.margin_type})"


# =============================================================================
# CUSTOMER DISCOUNTS
# =============================================================================

class CustomerDiscount(models.Model):
    """
    Customer-specific pricing adjustments per ProductCode.
    
    Supports multiple discount types:
    - PERCENTAGE: Reduce sell price by X% (e.g., 5% off airfreight)
    - FLAT_AMOUNT: Reduce sell price by fixed amount (e.g., K50 off per shipment)
    - RATE_REDUCTION: Override per-kg rate (e.g., K0.50/kg instead of K0.75/kg)
    - FIXED_CHARGE: Fixed total charge regardless of weight (e.g., K200 flat for docs)
    - MARGIN_OVERRIDE: Apply a specific margin % instead of standard (e.g., 15% margin instead of 20%)
    
    Business Rules:
    - Applied during pricing before GST calculation
    - Multiple discounts for same customer/product not allowed (unique_together)
    - Discount expires after valid_until date
    """
    
    # Discount type choices
    TYPE_PERCENTAGE = 'PERCENTAGE'
    TYPE_FLAT_AMOUNT = 'FLAT_AMOUNT'
    TYPE_RATE_REDUCTION = 'RATE_REDUCTION'
    TYPE_FIXED_CHARGE = 'FIXED_CHARGE'
    TYPE_MARGIN_OVERRIDE = 'MARGIN_OVERRIDE'
    
    DISCOUNT_TYPE_CHOICES = [
        (TYPE_PERCENTAGE, 'Percentage Discount (e.g., 5% off)'),
        (TYPE_FLAT_AMOUNT, 'Flat Amount Reduction (e.g., K50 off)'),
        (TYPE_RATE_REDUCTION, 'Rate Reduction (e.g., K0.50/kg instead of standard)'),
        (TYPE_FIXED_CHARGE, 'Fixed Charge (e.g., K200 flat regardless of weight)'),
        (TYPE_MARGIN_OVERRIDE, 'Margin Override (e.g., 15% margin instead of 20%)'),
    ]
    
    customer = models.ForeignKey(
        'parties.Company',
        on_delete=models.CASCADE,
        related_name='discounts',
        limit_choices_to={'company_type': 'CUSTOMER'},
        help_text='Customer company receiving the discount'
    )
    
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.CASCADE,
        related_name='customer_discounts',
        help_text='ProductCode this discount applies to'
    )
    
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default=TYPE_PERCENTAGE,
        help_text='Type of discount to apply'
    )
    
    # The meaning of this value depends on discount_type:
    # - PERCENTAGE: percentage value (e.g., 5.00 = 5%)
    # - FLAT_AMOUNT: currency amount to subtract (e.g., 50.00 = K50)
    # - RATE_REDUCTION: new rate per kg (e.g., 0.50 = K0.50/kg)
    # - FIXED_CHARGE: total charge amount (e.g., 200.00 = K200 flat)
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text='Discount value (meaning depends on discount_type)'
    )
    
    # Currency for FLAT_AMOUNT and FIXED_CHARGE types
    currency = models.CharField(
        max_length=3,
        default='PGK',
        help_text='Currency for FLAT_AMOUNT/FIXED_CHARGE types'
    )
    
    # Min/Max charges for RATE_REDUCTION type
    min_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Minimum charge for RATE_REDUCTION (e.g., 50.00 = K50 min)'
    )
    
    max_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Maximum charge cap for RATE_REDUCTION (e.g., 500.00 = K500 max)'
    )
    
    valid_from = models.DateField(
        null=True,
        blank=True,
        help_text='Discount starts from this date (null = immediately effective)'
    )
    
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text='Discount expires after this date (inclusive, null = no expiry)'
    )
    
    # Optional notes for commercial context
    notes = models.TextField(
        blank=True,
        help_text='Internal notes (e.g., "Negotiated Q1 2026 contract")'
    )
    
    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text='User who created this discount'
    )
    
    class Meta:
        db_table = 'customer_discounts'
        unique_together = ['customer', 'product_code']
        ordering = ['customer', 'product_code']
        verbose_name = 'Customer Discount'
        verbose_name_plural = 'Customer Discounts'
    
    def __str__(self):
        if self.discount_type == self.TYPE_PERCENTAGE:
            return f"{self.customer.name}: {self.discount_value}% off {self.product_code.code}"
        elif self.discount_type == self.TYPE_FLAT_AMOUNT:
            return f"{self.customer.name}: {self.currency}{self.discount_value} off {self.product_code.code}"
        elif self.discount_type == self.TYPE_RATE_REDUCTION:
            return f"{self.customer.name}: {self.currency}{self.discount_value}/kg for {self.product_code.code}"
        elif self.discount_type == self.TYPE_FIXED_CHARGE:
            return f"{self.customer.name}: Fixed {self.currency}{self.discount_value} for {self.product_code.code}"
        return f"{self.customer.name}: {self.product_code.code}"
    
    def clean(self):
        """Validate discount value based on type."""
        if self.discount_value is None:
            raise ValidationError("Discount value is required.")
            
        if self.discount_type == self.TYPE_PERCENTAGE:
            if self.discount_value < 0 or self.discount_value > 100:
                raise ValidationError("Percentage discount must be between 0 and 100.")
        else:
            if self.discount_value < 0:
                raise ValidationError("Discount value cannot be negative.")


# =============================================================================
# LOCAL RATE TABLES (One Commercial Truth for Origin/Destination Services)
# =============================================================================

class LocalSellRate(models.Model):
    """
    Centralized local sell rates - "One Commercial Truth" for origin/destination services.
    
    Purpose: What EFM CHARGES the customer for local services.
    
    Replaces:
    - Local portions of ExportSellRate (Origin charges)
    - Local portions of ImportSellRate (Destination charges)
    
    Design:
    - location: Single IATA code (origin for EXPORT, destination for IMPORT)
    - direction: EXPORT or IMPORT
    - payment_term: PREPAID, COLLECT, or ANY (applies to both)
    """
    
    DIRECTION_CHOICES = [
        ('EXPORT', 'Export (Origin Charges)'),
        ('IMPORT', 'Import (Destination Charges)'),
    ]
    
    PAYMENT_TERM_CHOICES = [
        ('PREPAID', 'Prepaid'),
        ('COLLECT', 'Collect'),
        ('ANY', 'Any Term'),
    ]
    
    RATE_TYPE_CHOICES = [
        ('FIXED', 'Fixed Per Shipment'),
        ('PER_KG', 'Per Kilogram'),
        ('PERCENT', 'Percentage of Component'),
    ]
    
    # Scope
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='local_sell_rates',
        help_text='The ProductCode this rate applies to'
    )
    location = models.CharField(
        max_length=3,
        db_index=True,
        help_text='IATA airport code (origin for EXPORT, destination for IMPORT)'
    )
    direction = models.CharField(
        max_length=6,
        choices=DIRECTION_CHOICES,
        db_index=True,
        help_text='EXPORT = origin charges, IMPORT = destination charges'
    )
    payment_term = models.CharField(
        max_length=7,
        choices=PAYMENT_TERM_CHOICES,
        default='ANY',
        db_index=True,
        help_text='PREPAID, COLLECT, or ANY (applies to both)'
    )
    
    # Commercials
    currency = models.CharField(max_length=3)
    rate_type = models.CharField(
        max_length=10,
        choices=RATE_TYPE_CHOICES,
        default='FIXED'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text='Rate amount (flat fee, per-kg rate, or percentage)'
    )
    # Additive support (per-kg + flat fee)
    is_additive = models.BooleanField(
        default=False,
        help_text='If True, adds a flat amount to the per-kg charge (PER_KG only).'
    )
    additive_flat_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Flat amount added when is_additive=True (PER_KG only).'
    )
    min_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Minimum charge (for per-kg rates)'
    )
    max_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Maximum charge (cap for per-kg rates)'
    )
    
    # Weight breaks for tiered pricing (e.g., cartage)
    weight_breaks = models.JSONField(
        null=True,
        blank=True,
        help_text='For tiered cartage rates: [{"min_kg": 0, "rate": "5.00"}, ...]'
    )
    
    # For PERCENT rate type (e.g., FSC = 10% of Cartage)
    percent_of_product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='local_sell_dependent_rates',
        help_text='For PERCENT type: the ProductCode this is a percentage of'
    )
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'local_sell_rates'
        unique_together = [
            'product_code', 'location', 'direction', 'payment_term', 'currency', 'valid_from'
        ]
        ordering = ['location', 'direction', 'product_code']
        verbose_name = 'Local Sell Rate'
        verbose_name_plural = 'Local Sell Rates'
    
    def __str__(self):
        return f"SELL: {self.product_code.code} @ {self.location} ({self.direction}, {self.payment_term})"

    def clean(self):
        if self.product_code and not is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is lane-based and must be stored in ExportSellRate/ImportSellRate."
            )
        if self.product_code and self.direction == 'EXPORT' and self.product_code.domain != ProductCode.DOMAIN_EXPORT:
            raise ValidationError("EXPORT local rates must reference Export ProductCodes (1xxx).")
        if self.product_code and self.direction == 'IMPORT' and self.product_code.domain != ProductCode.DOMAIN_IMPORT:
            raise ValidationError("IMPORT local rates must reference Import ProductCodes (2xxx).")

    # Compatibility helpers for shared pricing logic
    @property
    def rate_per_kg(self):
        if self.rate_type == 'PER_KG':
            return self.amount
        return None

    @property
    def rate_per_shipment(self):
        if self.rate_type == 'FIXED':
            return self.amount
        if self.rate_type == 'PER_KG' and self.is_additive:
            return self.additive_flat_amount
        return None

    @property
    def percent_rate(self):
        if self.rate_type == 'PERCENT':
            return self.amount
        return None


class LocalCOGSRate(models.Model):
    """
    Centralized local COGS rates - "One Commercial Truth" for origin/destination costs.
    
    Purpose: What EFM PAYS the vendor for local services.
    
    Replaces:
    - Local portions of ExportCOGS (Origin costs)
    - Local portions of ImportCOGS (Destination costs)
    
    Design:
    - location: Single IATA code (origin for EXPORT, destination for IMPORT)
    - direction: EXPORT or IMPORT
    - Counterparty: agent OR carrier (never both)
    """
    
    DIRECTION_CHOICES = [
        ('EXPORT', 'Export (Origin Costs)'),
        ('IMPORT', 'Import (Destination Costs)'),
    ]
    
    RATE_TYPE_CHOICES = [
        ('FIXED', 'Fixed Per Shipment'),
        ('PER_KG', 'Per Kilogram'),
        ('PERCENT', 'Percentage of Component'),
    ]
    
    # Scope
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='local_cogs_rates',
        help_text='The ProductCode this rate applies to'
    )
    location = models.CharField(
        max_length=3,
        db_index=True,
        help_text='IATA airport code (origin for EXPORT, destination for IMPORT)'
    )
    direction = models.CharField(
        max_length=6,
        choices=DIRECTION_CHOICES,
        db_index=True,
        help_text='EXPORT = origin costs, IMPORT = destination costs'
    )
    
    # Counterparty: agent OR carrier (never both, never null for both)
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='local_cogs_rates',
        help_text='For carrier-provided services'
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='local_cogs_rates',
        help_text='For agent-provided services (typical for local charges)'
    )
    
    # Commercials
    currency = models.CharField(max_length=3)
    rate_type = models.CharField(
        max_length=10,
        choices=RATE_TYPE_CHOICES,
        default='FIXED'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text='Rate amount (flat fee, per-kg rate, or percentage)'
    )
    # Additive support (per-kg + flat fee)
    is_additive = models.BooleanField(
        default=False,
        help_text='If True, adds a flat amount to the per-kg charge (PER_KG only).'
    )
    additive_flat_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Flat amount added when is_additive=True (PER_KG only).'
    )
    min_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Minimum charge (for per-kg rates)'
    )
    max_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Maximum charge (cap for per-kg rates)'
    )
    
    # Weight breaks for tiered pricing
    weight_breaks = models.JSONField(
        null=True,
        blank=True,
        help_text='For tiered rates: [{"min_kg": 0, "rate": "5.00"}, ...]'
    )
    
    # For PERCENT rate type (e.g., FSC = 20% of Pickup)
    percent_of_product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='local_cogs_dependent_rates',
        help_text='For PERCENT type: the ProductCode this is a percentage of'
    )
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'local_cogs_rates'
        ordering = ['location', 'direction', 'product_code']
        verbose_name = 'Local COGS Rate'
        verbose_name_plural = 'Local COGS Rates'
        constraints = [
            # Ensure exactly one counterparty (carrier XOR agent)
            models.CheckConstraint(
                check=(
                    models.Q(carrier__isnull=False, agent__isnull=True) |
                    models.Q(carrier__isnull=True, agent__isnull=False)
                ),
                name='local_cogs_one_counterparty'
            ),
        ]
    
    def clean(self):
        """Validate exactly one counterparty is set."""
        if self.carrier and self.agent:
            raise ValidationError("Cannot set both carrier and agent. Choose one.")
        if not self.carrier and not self.agent:
            raise ValidationError("Must set either carrier or agent.")
        if self.product_code and not is_local_rate_category(self.product_code.category):
            raise ValidationError(
                f"{self.product_code.code} is lane-based and must be stored in ExportCOGS/ImportCOGS."
            )
        if self.product_code and self.direction == 'EXPORT' and self.product_code.domain != ProductCode.DOMAIN_EXPORT:
            raise ValidationError("EXPORT local COGS rates must reference Export ProductCodes (1xxx).")
        if self.product_code and self.direction == 'IMPORT' and self.product_code.domain != ProductCode.DOMAIN_IMPORT:
            raise ValidationError("IMPORT local COGS rates must reference Import ProductCodes (2xxx).")
    
    def __str__(self):
        counterparty = self.carrier or self.agent
        return f"COGS: {self.product_code.code} @ {self.location} ({self.direction}) - {counterparty}"

    # Compatibility helpers for shared pricing logic
    @property
    def rate_per_kg(self):
        if self.rate_type == 'PER_KG':
            return self.amount
        return None

    @property
    def rate_per_shipment(self):
        if self.rate_type == 'FIXED':
            return self.amount
        if self.rate_type == 'PER_KG' and self.is_additive:
            return self.additive_flat_amount
        return None

    @property
    def percent_rate(self):
        if self.rate_type == 'PERCENT':
            return self.amount
        return None


class CommodityChargeRule(models.Model):
    """
    Data-driven commodity trigger rules for standard pricing availability.

    These rules do not calculate amounts themselves. They define which
    ProductCodes become relevant for a shipment when commodity, scope, and
    optional lane filters match.
    """

    SHIPMENT_TYPE_EXPORT = ProductCode.DOMAIN_EXPORT
    SHIPMENT_TYPE_IMPORT = ProductCode.DOMAIN_IMPORT
    SHIPMENT_TYPE_DOMESTIC = ProductCode.DOMAIN_DOMESTIC
    SHIPMENT_TYPE_CHOICES = ProductCode.DOMAIN_CHOICES

    SERVICE_SCOPE_A2A = 'A2A'
    SERVICE_SCOPE_A2D = 'A2D'
    SERVICE_SCOPE_D2A = 'D2A'
    SERVICE_SCOPE_D2D = 'D2D'
    SERVICE_SCOPE_CHOICES = [
        (SERVICE_SCOPE_A2A, 'Airport to Airport'),
        (SERVICE_SCOPE_A2D, 'Airport to Door'),
        (SERVICE_SCOPE_D2A, 'Door to Airport'),
        (SERVICE_SCOPE_D2D, 'Door to Door'),
    ]

    LEG_ORIGIN = 'ORIGIN'
    LEG_MAIN = 'MAIN'
    LEG_DESTINATION = 'DESTINATION'
    LEG_CHOICES = [
        (LEG_ORIGIN, 'Origin'),
        (LEG_MAIN, 'Main Freight'),
        (LEG_DESTINATION, 'Destination'),
    ]

    TRIGGER_MODE_AUTO = 'AUTO'
    TRIGGER_MODE_OPTIONAL = 'OPTIONAL'
    TRIGGER_MODE_REQUIRES_SPOT = 'REQUIRES_SPOT'
    TRIGGER_MODE_REQUIRES_MANUAL = 'REQUIRES_MANUAL'
    TRIGGER_MODE_CHOICES = [
        (TRIGGER_MODE_AUTO, 'Auto Include'),
        (TRIGGER_MODE_OPTIONAL, 'Optional'),
        (TRIGGER_MODE_REQUIRES_SPOT, 'Requires SPOT'),
        (TRIGGER_MODE_REQUIRES_MANUAL, 'Requires Manual Entry'),
    ]

    PAYMENT_TERM_PREPAID = 'PREPAID'
    PAYMENT_TERM_COLLECT = 'COLLECT'
    PAYMENT_TERM_CHOICES = [
        (PAYMENT_TERM_PREPAID, 'Prepaid'),
        (PAYMENT_TERM_COLLECT, 'Collect'),
    ]

    shipment_type = models.CharField(max_length=10, choices=SHIPMENT_TYPE_CHOICES, db_index=True)
    service_scope = models.CharField(max_length=3, choices=SERVICE_SCOPE_CHOICES, db_index=True)
    commodity_code = models.CharField(
        max_length=10,
        choices=COMMODITY_CHOICES,
        default=DEFAULT_COMMODITY_CODE,
        db_index=True,
    )
    product_code = models.ForeignKey(
        ProductCode,
        on_delete=models.PROTECT,
        related_name='commodity_charge_rules',
    )
    leg = models.CharField(max_length=11, choices=LEG_CHOICES, db_index=True)
    trigger_mode = models.CharField(max_length=20, choices=TRIGGER_MODE_CHOICES, default=TRIGGER_MODE_AUTO)
    origin_code = models.CharField(max_length=3, null=True, blank=True, db_index=True)
    destination_code = models.CharField(max_length=3, null=True, blank=True, db_index=True)
    payment_term = models.CharField(
        max_length=10,
        choices=PAYMENT_TERM_CHOICES,
        null=True,
        blank=True,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'commodity_charge_rules'
        ordering = ['shipment_type', 'service_scope', 'commodity_code', 'product_code__id']
        verbose_name = 'Commodity Charge Rule'
        verbose_name_plural = 'Commodity Charge Rules'
        indexes = [
            models.Index(
                fields=['shipment_type', 'service_scope', 'commodity_code', 'is_active'],
                name='commodity_rule_lookup_idx',
            ),
            models.Index(
                fields=['origin_code', 'destination_code', 'payment_term'],
                name='commodity_rule_lane_idx',
            ),
        ]

    def clean(self):
        if self.product_code and self.product_code.domain != self.shipment_type:
            raise ValidationError(
                {
                    'product_code': (
                        f"{self.shipment_type} commodity rules must reference "
                        f"{self.shipment_type.lower()} ProductCodes."
                    )
                }
            )

        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({'effective_to': 'effective_to must be on or after effective_from.'})

    def __str__(self):
        lane = []
        if self.origin_code:
            lane.append(self.origin_code)
        if self.destination_code:
            lane.append(self.destination_code)
        lane_display = " -> ".join(lane) if lane else "ALL LANES"
        return (
            f"{self.shipment_type} {self.service_scope} {self.commodity_code} "
            f"{self.product_code.code} ({self.trigger_mode}) [{lane_display}]"
        )

