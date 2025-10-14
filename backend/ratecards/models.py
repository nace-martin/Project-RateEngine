from django.db import models

class RatecardFile(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='ratecards/')
    file_type = models.CharField(max_length=50, choices=[('CSV', 'CSV'), ('HTML', 'HTML')])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Rate(models.Model):
    rate_card = models.ForeignKey(RatecardFile, on_delete=models.CASCADE, related_name='rates')
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    min_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    max_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_kg = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.origin} to {self.destination} - {self.rate_per_kg}/kg'