from django.db import models


class Quotes(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey('organizations.Organizations', models.PROTECT)
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
    quote = models.ForeignKey('quotes.Quotes', models.CASCADE, related_name='lines')
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
