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
from django.db import models
from django.core.exceptions import ValidationError


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
        unique_together = ['product_code', 'origin_airport', 'destination_airport', 'valid_from']
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Export Sell Rate'
        verbose_name_plural = 'Export Sell Rates'
    
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
        unique_together = ['product_code', 'origin_airport', 'destination_airport', 'valid_from']
        ordering = ['product_code', 'origin_airport', 'destination_airport']
        verbose_name = 'Import Sell Rate'
        verbose_name_plural = 'Import Sell Rates'
    
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
    
    # Domestic COGS references an agent (local service provider)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.PROTECT,
        related_name='domestic_cogs_rates',
        help_text='Local service provider'
    )
    
    # Rate values - domestic is always PGK
    currency = models.CharField(max_length=3, default='PGK')
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rate_per_shipment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Additive calculation flag
    is_additive = models.BooleanField(default=False)
    
    # Validity
    valid_from = models.DateField()
    valid_until = models.DateField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'domestic_cogs'
        unique_together = ['product_code', 'origin_zone', 'destination_zone', 'agent', 'valid_from']
        ordering = ['product_code', 'origin_zone', 'destination_zone']
        verbose_name = 'Domestic COGS'
        verbose_name_plural = 'Domestic COGS'
    
    def __str__(self):
        return f"COGS: {self.product_code.code} {self.origin_zone}→{self.destination_zone} ({self.agent})"


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
