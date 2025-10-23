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

class ServiceComponent(models.Model):
    """
    Represents a granular, billable service component (e.g., pickup, clearance, freight).
    Stores base costs and rules.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=20, unique=True, db_index=True,
        help_text="Short, unique, stable code (e.g., 'PKUP_ORG', 'CLEAR_IMP', 'FRT_AIR')."
    )
    description = models.CharField(max_length=255)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    leg = models.CharField(max_length=20, choices=LEG_CHOICES, db_index=True)
    base_pgk_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.0"),
        help_text="Standard internal cost for this service in PGK."
    )
    unit = models.CharField(
        max_length=20, choices=UNIT_CHOICES, default='SHIPMENT',
        help_text="The unit basis for the base_pgk_cost (e.g., Per KG, Per Shipment)."
    )
    min_charge_pgk = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Minimum cost applied for this component in PGK."
    )
    # Tiering/Weight Breaks - Stored as JSON for flexibility
    # Example: [{"min_kg": 0, "max_kg": 100, "rate": 5.50}, {"min_kg": 100, "rate": 4.50}]
    # Example: [{"min_cbm": 0, "max_cbm": 1, "rate": 150.00}, ...]
    tiering_json = models.JSONField(
        null=True, blank=True,
        help_text="JSON defining tiered pricing rules (e.g., weight breaks, CBM breaks)."
    )
    audience = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default='BOTH',
        help_text="Is this primarily a Buy cost, Sell charge, or both?"
    )
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, # Optional: Use choices
        null=True, blank=True, db_index=True,
        help_text="Category for grouping charges on quotes/invoices."
    )
    tax_code = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Tax code reference (e.g., 'GST_10', 'ZERO_RATED')."
    )
    # Store the rate directly for simplicity, can be linked to a TaxRate model later
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, db_index=True)
    shipment_type = models.CharField(
        max_length=10, choices=[('IMPORT', 'Import'), ('EXPORT', 'Export'), ('DOMESTIC', 'Domestic')],
        db_index=True
    )
    # Using CharField for Incoterm code flexibility
    incoterm = models.CharField(max_length=3, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    # ManyToManyField defines the set of services included for this rule
    service_components = models.ManyToManyField(
        ServiceComponent,
        related_name='incoterm_rules',
        help_text="Select the services included in the scope for this Incoterm rule."
    )

    # Optional: More complex rules could go here later, e.g., JSON logic
    # leg_rules_json = models.JSONField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.mode} {self.shipment_type} {self.incoterm}"

    class Meta:
        unique_together = ('mode', 'shipment_type', 'incoterm')
        ordering = ['mode', 'shipment_type', 'incoterm']
        verbose_name = "Incoterm Rule"
        verbose_name_plural = "Incoterm Rules"