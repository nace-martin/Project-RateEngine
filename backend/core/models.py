from django.core.validators import RegexValidator
from django.db import models


CURRENCY_CODE_VALIDATOR = RegexValidator(
    regex=r'^[A-Z]{3}$',
    message='Currency code must be a three-letter ISO 4217 code.',
)


class Providers(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True)
    provider_type = models.TextField()

    class Meta:
        db_table = 'providers'


class Stations(models.Model):
    id = models.BigAutoField(primary_key=True)
    iata = models.TextField(unique=True)
    city = models.TextField(blank=True, null=True)
    country = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'stations'


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
        db_table = 'currency_rates'
        unique_together = (('as_of_ts', 'base_ccy', 'quote_ccy', 'rate_type'),)


class FeeTypes(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.TextField(unique=True)
    description = models.TextField()
    basis = models.TextField()
    default_tax_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = 'fee_types'


class Services(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.TextField(unique=True)
    name = models.TextField()
    basis = models.TextField()

    class Meta:
        db_table = 'services'
