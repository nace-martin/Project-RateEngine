from django.db import models

class RatecardFile(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='ratecards/')
    file_type = models.CharField(max_length=50, choices=[('CSV', 'CSV'), ('HTML', 'HTML')])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name