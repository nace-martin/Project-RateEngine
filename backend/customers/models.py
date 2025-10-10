from django.db import models
from django.db.models import UniqueConstraint

class Address(models.Model):
    address_line_1 = models.CharField(max_length=255, blank=True, null=True)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state_province = models.CharField(max_length=100, blank=True, null=True, verbose_name="State / Province")
    postcode = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Addresses"
        constraints = [
            UniqueConstraint(fields=['address_line_1', 'address_line_2', 'city', 'state_province', 'postcode', 'country'], name='unique_address')
        ]

    def __str__(self):
        return f"{self.address_line_1}, {self.city}, {self.country}"

class Customer(models.Model):
    AUDIENCE_CHOICES = [
        ('LOCAL_PNG_CUSTOMER', 'Local PNG Customer'),
        ('OVERSEAS_PARTNER_AU', 'Overseas Partner (AU)'),
        ('OVERSEAS_PARTNER_NON_AU', 'Overseas Partner (Non-AU)'),
    ]

    company_name = models.CharField(max_length=255, unique=True)
    audience_type = models.CharField(max_length=50, choices=AUDIENCE_CHOICES, default='LOCAL_PNG_CUSTOMER')
    
    # Link to the new Address model
    primary_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name='customers')

    # Flexible address field for PNG
    address_description = models.TextField(blank=True, null=True, help_text="For PNG addresses without formal structure, e.g., 'Warehouse next to the main market, Gordons'")

    # Contact person details
    contact_person_name = models.CharField(max_length=255, blank=True, null=True)
    contact_person_email = models.EmailField(max_length=254, blank=True, null=True)
    contact_person_phone = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.company_name