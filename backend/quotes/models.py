# backend/quotes/models.py

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from parties.models import Company
from core.models import Policy, FxSnapshot

class Quote(models.Model):
    """
    Main quote object. Stores the high-level request, links to the rulesets used,
    and holds the final calculated totals.
    """
    class Scenario(models.TextChoices):
        IMP_D2D_COLLECT = 'IMPORT_D2D_COLLECT', _('Import D2D Collect')
        IMP_A2D_AGENT = 'IMPORT_A2D_AGENT_AUD', _('Import A2D Agent (AUD)')
        EXP_D2A_COLLECT = 'EXPORT_D2A_COLLECT', _('Export D2A Collect')
        EXP_D2A_PREPAID = 'EXPORT_D2A_PREPAID', _('Export D2A Prepaid')
        EXP_D2D_COLLECT = 'EXPORT_D2D_COLLECT', _('Export D2D Collect')
        EXP_D2D_PREPAID = 'EXPORT_D2D_PREPAID', _('Export D2D Prepaid')

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        FINAL = 'FINAL', _('Finalized')
        SENT = 'SENT', _('Sent to Customer')
        ARCHIVED = 'ARCHIVED', _('Archived')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote_number = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated human-readable ID.")
    
    # Parties involved
    bill_to = models.ForeignKey(Company, related_name='quotes_billed', on_delete=models.SET_NULL, null=True, blank=True)
    shipper = models.ForeignKey(Company, related_name='quotes_shipped', on_delete=models.SET_NULL, null=True, blank=True)
    consignee = models.ForeignKey(Company, related_name='quotes_consigned', on_delete=models.SET_NULL, null=True, blank=True)

    # Auditability Links
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, help_text="The exact policy version used for this quote.")
    fx_snapshot = models.ForeignKey(FxSnapshot, on_delete=models.PROTECT, help_text="The exact FX snapshot used for this quote.")
    
    # Core Request & Response
    scenario = models.CharField(max_length=50, choices=Scenario.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    request_details = models.JSONField(help_text="Original request payload from the user.")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.quote_number

    def save(self, *args, **kwargs):
        if not self.quote_number:
            # A simple sequence for human-readable IDs. Could be more robust.
            last_quote = Quote.objects.all().order_by('created_at').last()
            last_id = int(last_quote.quote_number.split('-')[1]) if last_quote else 1000
            self.quote_number = f"QT-{last_id + 1}"
        super().save(*args, **kwargs)


class QuoteLine(models.Model):
    """
    A single, auditable line item within a quote. This replaces the old QuoteCharge model.
    It stores not just the result, but how we got there.
    """
    class Section(models.TextChoices):
        ORIGIN = 'ORIGIN', _('Origin')
        FREIGHT = 'FREIGHT', _('Freight')
        DESTINATION = 'DESTINATION', _('Destination')
        INFO_ONLY = 'INFO_ONLY', _('Informational Only')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(Quote, related_name='lines', on_delete=models.CASCADE)
    section = models.CharField(max_length=20, choices=Section.choices)
    charge_code = models.CharField(max_length=50, help_text="e.g., 'FREIGHT', 'CARTAGE', 'AW'")
    description = models.CharField(max_length=255)
    
    # Calculation Inputs
    basis = models.CharField(max_length=50) # e.g., 'PER_KG', 'FLAT', '120.0 kg @ 5.60/kg'
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=4)
    currency = models.CharField(max_length=3)
    
    # Calculation Outputs
    buy_amount_native = models.DecimalField(max_digits=12, decimal_places=2)
    sell_amount_pgk = models.DecimalField(max_digits=12, decimal_places=2)
    gst_amount_pgk = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    
    # Audit Flags & Data
    caf_applied_pct = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    margin_applied_pct = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    rounding_applied = models.BooleanField(default=False)
    source_references = models.JSONField(help_text="Links to source tables, e.g., {'surcharge_id': '...', 'ratecard_break_id': '...'}")

    def __str__(self):
        return f"{self.quote.quote_number} - {self.description}"


class QuoteTotal(models.Model):
    """
    Final totals for the quote. Stored separately for clarity.
    """
    quote = models.OneToOneField(Quote, primary_key=True, related_name='totals', on_delete=models.CASCADE)
    subtotal_pgk = models.DecimalField(max_digits=12, decimal_places=2)
    gst_total_pgk = models.DecimalField(max_digits=12, decimal_places=2)
    grand_total_pgk = models.DecimalField(max_digits=12, decimal_places=2)
    output_currency = models.CharField(max_length=3, default='PGK') # For agent quotes in AUD
    grand_total_output_currency = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Totals for {self.quote.quote_number}"