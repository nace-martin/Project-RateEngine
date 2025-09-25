from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Address(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='addresses')
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    province = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=True)

class Contact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=255, blank=True, null=True)
    is_primary = models.BooleanField(default=True)