# backend/accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('sales', 'Sales'),
        ('manager', 'Manager'),
        ('finance', 'Finance'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='sales')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"