# backend/parties/models.py

import uuid
from django.db import models
from core.models import Country, City, Currency
from django.conf import settings # For AUTH_USER_MODEL
from decimal import Decimal # Import Decimal

class Company(models.Model):
    AUDIENCE_LOCAL_PNG = 'LOCAL_PNG_CUSTOMER'
    AUDIENCE_OVERSEAS_AU = 'OVERSEAS_PARTNER_AU'
    AUDIENCE_OVERSEAS_NON_AU = 'OVERSEAS_PARTNER_NON_AU'
    AUDIENCE_TYPE_CHOICES = [
        (AUDIENCE_LOCAL_PNG, 'Local PNG Customer'),
        (AUDIENCE_OVERSEAS_AU, 'Overseas Partner (AU)'),
        (AUDIENCE_OVERSEAS_NON_AU, 'Overseas Partner (Non-AU)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    audience_type = models.CharField(
        max_length=32,
        choices=AUDIENCE_TYPE_CHOICES,
        default=AUDIENCE_LOCAL_PNG,
    )
    address_description = models.CharField(max_length=255, blank=True, default='')
    
    # New flags replacing company_type
    is_customer = models.BooleanField(default=False)
    is_agent = models.BooleanField(default=False) 
    is_carrier = models.BooleanField(default=False)
    
    # Deprecated - to be removed after data migration
    company_type = models.CharField(max_length=20, choices=[('CUSTOMER', 'Customer'), ('SUPPLIER', 'Supplier')], default='CUSTOMER', null=True, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Companies"

class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, related_name='addresses', on_delete=models.CASCADE)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.ForeignKey(City, on_delete=models.PROTECT)
    country = models.ForeignKey(Country, on_delete=models.PROTECT)
    postal_code = models.CharField(max_length=20, blank=True)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.address_line_1}, {self.city}"

class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, related_name='contacts', on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.company.name})"

# --- ADD THIS NEW MODEL ---
class CustomerCommercialProfile(models.Model):
    """
    Stores customer-specific commercial terms like preferred currency,
    margins, and potentially payment/incoterm defaults.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name='commercial_profile'
    )
    preferred_quote_currency = models.ForeignKey(
        Currency,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="Default currency for quoting this customer (e.g., AUD, USD)."
    )
    default_margin_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Override standard margin for this customer (e.g., 12.00 for 12%)."
    )
    min_margin_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Minimum allowable margin for quotes to this customer."
    )
    # Add defaults based on suggestions - allowing null for flexibility
    payment_term_default = models.CharField(
        max_length=10, # PREPAID / COLLECT
        choices=[('PREPAID', 'Prepaid'), ('COLLECT', 'Collect')],
        null=True, blank=True,
        help_text="Default payment term if known."
    )
    # Incoterm whitelist might be better as a separate M2M or JSON field later
    # incoterm_whitelist = models.JSONField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )

    def __str__(self):
        return f"Commercial Profile for {self.company.name}"

    class Meta:
        verbose_name = "Customer Commercial Profile"
        verbose_name_plural = "Customer Commercial Profiles"

# --- END ADD ---
