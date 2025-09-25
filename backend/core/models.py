from django.db import models

class Company(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    phone = models.CharField(max_length=255)
    email = models.EmailField()
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)

class Station(models.Model):
    iata_code = models.CharField(max_length=3, unique=True)
    city = models.CharField(max_length=255)
    country_code = models.CharField(max_length=2)

    def __str__(self):
        return f"{self.iata_code} ({self.city}, {self.country_code})"