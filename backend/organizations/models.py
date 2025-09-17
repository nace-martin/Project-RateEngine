from django.db import models


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
        db_table = 'organizations'


class Contacts(models.Model):
    id = models.BigAutoField(primary_key=True)
    org = models.ForeignKey('organizations.Organizations', models.DO_NOTHING)
    name = models.TextField()
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'contacts'


class Sites(models.Model):
    id = models.BigAutoField(primary_key=True)
    org = models.ForeignKey('organizations.Organizations', models.DO_NOTHING)
    label = models.TextField()
    address = models.TextField()
    city = models.TextField(blank=True, null=True)
    province = models.TextField(blank=True, null=True)
    country = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sites'

