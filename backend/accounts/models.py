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


class OrganizationMembership(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='org_memberships')
    organization = models.ForeignKey('rate_engine.Organizations', on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, default='sales')
    can_quote = models.BooleanField(default=True)
    can_view_costs = models.BooleanField(default=False)
    is_primary_contact = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'organization'),)

    def __str__(self):
        return f"{self.user.username} -> {self.organization_id} ({self.role})"
