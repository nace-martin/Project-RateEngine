# backend/services/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

# Choices for reusable fields
MODE_CHOICES = [('AIR', 'Air'), ('SEA', 'Sea'), ('LAND', 'Land')]
LEG_CHOICES = [('ORIGIN', 'Origin'), ('MAIN', 'Main Freight'), ('DESTINATION', 'Destination')]
UNIT_CHOICES = [
    ('SHIPMENT', 'Per Shipment'),
    ('KG', 'Per KG'),
    ('WM', 'Per W/M'), # Weight/Measurement for LCL Sea
    ('CBM', 'Per CBM'),
    ('TEU', 'Per TEU'), # Twenty-foot Equivalent Unit (FCL Sea)
    ('FEU', 'Per FEU'), # Forty-foot Equivalent Unit (FCL Sea)
    ('PALLET', 'Per Pallet'),
    ('KM', 'Per KM'),
    ('PAGE', 'Per Page'),
]
AUDIENCE_CHOICES = [('BUY', 'Buy Side'), ('SELL', 'Sell Side'), ('BOTH', 'Both')]
SHIPMENT_DIRECTION_CHOICES = [
    ('IMPORT', 'Import'),
    ('EXPORT', 'Export'),
    ('DOMESTIC', 'Domestic'),
]
PAYMENT_TERM_CHOICES = [
    ('PREPAID', 'Prepaid'),
    ('COLLECT', 'Collect'),
]
SERVICE_SCOPE_CHOICES = [
    ('D2D', 'Door to Door'),
    ('D2A', 'Door to Airport'),
    ('A2D', 'Airport to Door'),
    ('A2A', 'Airport to Airport'),
]
OUTPUT_CURRENCY_TYPE_CHOICES = [
    ('DESTINATION', 'Match Destination Currency'),
    ('ORIGIN', 'Match Origin Currency'),
    ('PGK', 'Force PGK'),
    ('USD', 'Force USD'),
]
LEG_OWNER_CHOICES = [
    ('COMPANY', 'Company Managed'),
    ('CUSTOMER', 'Customer Managed'),
    ('THIRD_PARTY', '3rd Party / Partner'),
]

# Optional: Define choices for category for consistency
CATEGORY_CHOICES = [
    ('TRANSPORT', 'Transportation / Freight'),
    ('HANDLING', 'Handling / Terminal'),
    ('CUSTOMS', 'Customs / Regulatory'),
    ('DOCUMENTATION', 'Documentation'),
    ('LOCAL', 'Local / Cartage'),
    ('ACCESSORIAL', 'Accessorial / Other'),
    ('STATUTORY', 'Statutory / Pass-Through'),
]

# --- NEW: Choices for Cost Type ---
COST_TYPE_CHOICES = [
    ('COGS', 'COGS (Cost - Requires Lookup or Base)'),
    ('RATE_OFFER', 'Rate Offer (Sell Price - Requires Lookup or Base)'),
]
# ---

# --- NEW: Choices for Cost Source ---
COST_SOURCE_CHOICES = [
    ('BASE_COST', 'Base PGK Cost (Directly from this ServiceComponent)'),
    ('EXPORT_RATECARD', 'Export Rate Card (e.g., ratecards.RateCard)'),
    ('PARTNER_RATECARD', 'Partner Rate Card (e.g., Import AUD Rates - Requires New Model)'),
    ('LOCAL_TARIFF', 'Local Tariff (e.g., core.LocalTariff - PNG Sell Rates)'),
    ('SURCHARGE', 'Surcharge Table (e.g., core.Surcharge - PX Fees)'),
    # Add more sources as needed (e.g., SPOT_RATE, MANUAL_INPUT)
]
# ---

# --- NEW: Choices for Pricing Method (Service Codes) ---
PRICING_METHOD_CHOICES = [
    ('FX_CAF_MARGIN', 'FX + CAF + Margin (Origin Charges)'),
    ('PASSTHROUGH', 'Pass-through (Destination Charges)'),
    ('RATE_OF_BASE', 'Percentage of Base (Fuel Surcharges)'),
    ('STANDARD_RATE', 'Standard Rate (Freight)'),
]

SERVICE_CATEGORY_CHOICES = [
    ('PICKUP', 'Pickup & Collection'),
    ('DELIVERY', 'Delivery & Cartage'),
    ('CLEARANCE', 'Customs Clearance'),
    ('FREIGHT', 'Main Freight'),
    ('HANDLING', 'Handling & Terminal'),
    ('DOCUMENTATION', 'Documentation Fees'),
    ('AGENCY', 'Agency Fees'),
    ('SCREENING', 'Security & Screening'),
    ('FUEL_SURCHARGE', 'Fuel Surcharge'),
    ('OTHER', 'Other Charges'),
]
# ---


class ServiceCode(models.Model):
    """
    Master table for service codes with embedded classification and GL mapping.
    Replaces ad-hoc categorization logic with deterministic service code classification.
    """
    code = models.CharField(
        max_length=20, 
        unique=True, 
        primary_key=True,
        help_text="Service code in format [LOCATION]-[TYPE]-[SUBTYPE], e.g., 'ORG-PICKUP-STD'"
    )
    description = models.CharField(
        max_length=200,
        help_text="Human-readable description of this service"
    )
    
    # Classification
    location_type = models.CharField(
        max_length=20,
        choices=LEG_CHOICES,
        db_index=True,
        help_text="Where this service is performed: ORIGIN, MAIN, or DESTINATION"
    )
    service_category = models.CharField(
        max_length=50,
        choices=SERVICE_CATEGORY_CHOICES,
        db_index=True,
        help_text="Category of service for grouping and reporting"
    )
    
    # Pricing Logic
    pricing_method = models.CharField(
        max_length=20,
        choices=PRICING_METHOD_CHOICES,
        help_text="How this service should be priced by the engine"
    )
    
    # Tax & Accounting
    is_taxable = models.BooleanField(
        default=True,
        help_text="Whether GST/VAT applies to this service"
    )
    gl_code = models.CharField(
        max_length=20, 
        null=True, 
        blank=True,
        help_text="General Ledger code for accounting integration"
    )
    revenue_account = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text="Revenue account code"
    )
    cost_account = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text="Cost account code"
    )
    
    # Validation Rules
    requires_weight = models.BooleanField(
        default=False,
        help_text="Whether this service requires weight information"
    )
    requires_dimensions = models.BooleanField(
        default=False,
        help_text="Whether this service requires dimension information"
    )
    is_mandatory = models.BooleanField(
        default=False,
        help_text="Whether this service must be included in quotes"
    )
    
    # Metadata
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this service code is currently in use"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Internal notes about this service code"
    )
    
    class Meta:
        db_table = 'service_codes'
        ordering = ['code']
        verbose_name = 'Service Code'
        verbose_name_plural = 'Service Codes'
    
    def __str__(self):
        return f"{self.code} - {self.description}"
    
    def clean(self):
        """Validate service code format"""
        from django.core.exceptions import ValidationError
        if not self.code:
            return
        
        # Validate code format: XXX-XXXX-XXX
        parts = self.code.split('-')
        if len(parts) < 2:
            raise ValidationError(f"Service code must be in format [LOCATION]-[TYPE]-[SUBTYPE]: {self.code}")
        
        # Validate location prefix matches location_type
        location_prefix_map = {
            'ORIGIN': 'ORG',
            'MAIN': 'FRT',
            'DESTINATION': 'DST'
        }
        expected_prefix = location_prefix_map.get(self.location_type)
        if expected_prefix and not self.code.startswith(expected_prefix):
            raise ValidationError(
                f"Service code for {self.location_type} should start with '{expected_prefix}': {self.code}"
            )



class ServiceComponent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, db_index=True, help_text="Short, unique, stable code (e.g., 'PKUP_ORG', 'CLEAR_IMP', 'FRT_AIR').")
    description = models.CharField(max_length=255, unique=True)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    leg = models.CharField(max_length=20, choices=LEG_CHOICES, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, null=True, blank=True, db_index=True, help_text="Category for grouping charges on quotes/invoices.")

    # --- Phase 2: Service Code Integration ---
    service_code = models.ForeignKey(
        ServiceCode,
        on_delete=models.PROTECT,
        related_name='components',
        null=True,
        blank=True,
        db_index=True,
        help_text="Service code for deterministic classification (Phase 2). Nullable for backward compatibility."
    )
    # ---

    # --- ADD cost_type field ---
    cost_type = models.CharField(
        max_length=10,
        choices=COST_TYPE_CHOICES,
        default='COGS', # Default to COGS, adjust as needed
        help_text="Is this a direct cost (COGS) or a standard sell rate (Rate Offer)?"
    )
    # ---

    # --- ADD cost_source field ---
    cost_source = models.CharField(
        max_length=20,
        choices=COST_SOURCE_CHOICES,
        default='BASE_COST', # Default to using base_pgk_cost
        help_text="Where does the system find the cost/rate for this service?"
    )
    # ---

    base_pgk_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.0"),
        help_text="Standard internal cost or sell rate in PGK (used if cost_source is BASE_COST)."
    )
    cost_currency_type = models.CharField( # Keep this to flag if source is FCY
        max_length=3,
        choices=[('PGK', 'PGK'), ('FCY', 'FCY')],
        default='PGK',
        help_text="Currency type if cost_source requires lookup (e.g., PARTNER_RATECARD often FCY)."
    )
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='SHIPMENT', help_text="The unit basis for the cost/rate.")
    min_charge_pgk = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Minimum charge applied in PGK.")
    tiering_json = models.JSONField(null=True, blank=True, help_text="JSON defining tiered pricing rules.")
    audience = models.CharField(max_length=10, choices=AUDIENCE_CHOICES, default='BOTH')
    tax_code = models.CharField(max_length=20, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.0"))
    
    # --- Percentage Surcharge Support ---
    percent_of_component = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surcharges',
        help_text="If this is a percentage surcharge, reference the base component (e.g., Fuel Surcharge = 10%% of Cartage)"
    )
    percent_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage value (e.g., 10.00 for 10%%). Only used if percent_of_component is set."
    )
    # ---
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.description})"

    class Meta:
        ordering = ['mode', 'leg', 'code']


class ServiceRule(models.Model):
    """
    Defines the full routing/quoting scope for a given combination of mode,
    direction, incoterm, payment term, and user-selected service scope.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    direction = models.CharField(max_length=10, choices=SHIPMENT_DIRECTION_CHOICES, db_index=True)
    incoterm = models.CharField(max_length=3, null=True, blank=True, db_index=True)
    payment_term = models.CharField(max_length=10, choices=PAYMENT_TERM_CHOICES, db_index=True)
    service_scope = models.CharField(max_length=3, choices=SERVICE_SCOPE_CHOICES, db_index=True)
    description = models.CharField(max_length=255, blank=True)

    output_currency_type = models.CharField(
        max_length=20,
        choices=OUTPUT_CURRENCY_TYPE_CHOICES,
        default='DESTINATION',
        help_text="Determines how the sell/output currency should be derived."
    )
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)

    service_components = models.ManyToManyField(
        ServiceComponent,
        through='ServiceRuleComponent',
        related_name='service_rules'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.mode} {self.direction} {self.incoterm or 'N/A'} {self.payment_term} {self.service_scope}"

    class Meta:
        unique_together = ('mode', 'direction', 'incoterm', 'payment_term', 'service_scope')
        ordering = ['mode', 'direction', 'incoterm', 'payment_term', 'service_scope']
        verbose_name = "Service Rule"
        verbose_name_plural = "Service Rules"


class ServiceRuleComponent(models.Model):
    """
    Through table linking ServiceRules to ServiceComponents with ownership metadata.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_rule = models.ForeignKey(ServiceRule, on_delete=models.CASCADE, related_name='rule_components')
    service_component = models.ForeignKey(ServiceComponent, on_delete=models.CASCADE, related_name='component_rules')
    sequence = models.PositiveIntegerField(default=0, help_text="Ordering of the component within the rule.")
    leg_owner = models.CharField(
        max_length=20,
        choices=LEG_OWNER_CHOICES,
        default='COMPANY',
        help_text="Who owns/manages this component within the scope."
    )
    is_mandatory = models.BooleanField(default=True, help_text="Marks whether the component is required for the scope.")
    notes = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('service_rule', 'service_component')
        ordering = ['service_rule', 'sequence', 'service_component__code']
        verbose_name = "Service Rule Component"
        verbose_name_plural = "Service Rule Components"

    def __str__(self):
        return f"{self.service_rule} -> {self.service_component}"
