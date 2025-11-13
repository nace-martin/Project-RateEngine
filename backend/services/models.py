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
]
AUDIENCE_CHOICES = [('BUY', 'Buy Side'), ('SELL', 'Sell Side'), ('BOTH', 'Both')]

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

class ServiceComponent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, db_index=True, help_text="Short, unique, stable code (e.g., 'PKUP_ORG', 'CLEAR_IMP', 'FRT_AIR').")
    description = models.CharField(max_length=255, unique=True)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    leg = models.CharField(max_length=20, choices=LEG_CHOICES, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, null=True, blank=True, db_index=True, help_text="Category for grouping charges on quotes/invoices.")

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
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.description})"

    class Meta:
        ordering = ['mode', 'leg', 'code']


class IncotermRule(models.Model):
    """
    Maps a combination of Mode, Shipment Type, and Incoterm to the set of
    ServiceComponents that are typically included in the scope of work.
    """
    SERVICE_LEVEL_CHOICES = [
        ('D2D', 'Door-to-Door'),
        ('A2D', 'Airport-to-Door'),
        ('D2A', 'Door-to-Airport'),
        ('A2A', 'Airport-to-Airport'),
    ]
    PAYMENT_TERM_CHOICES = [
        ('PREPAID', 'Prepaid'),
        ('COLLECT', 'Collect'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    shipment_type = models.CharField(
        max_length=10, choices=[('IMPORT', 'Import'), ('EXPORT', 'Export'), ('DOMESTIC', 'Domestic')],
        db_index=True
    )
    incoterm = models.CharField(max_length=3, db_index=True)
    service_level = models.CharField(max_length=3, choices=SERVICE_LEVEL_CHOICES, db_index=True, default='D2D')
    payment_term = models.CharField(max_length=10, choices=PAYMENT_TERM_CHOICES, db_index=True, default='PREPAID')
    description = models.CharField(max_length=255, blank=True)
    service_components = models.ManyToManyField(
        ServiceComponent,
        related_name='incoterm_rules',
        help_text="Select the services included in the scope for this Incoterm rule."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.mode} {self.shipment_type} {self.incoterm} {self.service_level} {self.payment_term}"

    class Meta:
        unique_together = ('mode', 'shipment_type', 'incoterm', 'service_level', 'payment_term')
        ordering = ['mode', 'shipment_type', 'incoterm', 'service_level', 'payment_term']
        verbose_name = "Incoterm Rule"
        verbose_name_plural = "Incoterm Rules"