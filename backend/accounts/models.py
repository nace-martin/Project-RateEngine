# backend/accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Custom user model with role-based access control.
    
    Roles:
        SALES - Can create/edit quotes, cannot see COGS/margins
        MANAGER - Full quote access, can see COGS/margins, manage rate cards
        FINANCE - Can see COGS/margins, manage FX rates, cannot edit quotes
        ADMIN - Full system access
    """
    
    # Role constants for use across the application
    ROLE_SALES = 'sales'
    ROLE_MANAGER = 'manager'
    ROLE_FINANCE = 'finance'
    ROLE_ADMIN = 'admin'
    
    ROLE_CHOICES = [
        (ROLE_SALES, 'Sales'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_FINANCE, 'Finance'),
        (ROLE_ADMIN, 'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_SALES)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='customuser_set',
        related_query_name='customuser',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='customuser_set',
        related_query_name='customuser',
    )
    
    DEPARTMENT_CHOICES = [
        ('AIR', 'Air Freight'),
        ('SEA', 'Sea Freight'),
        ('LAND', 'Land Freight'),
    ]
    department = models.CharField(
        max_length=10, 
        choices=DEPARTMENT_CHOICES, 
        null=True, 
        blank=True,
        help_text="Department assignment for visibility restrictions (e.g., Air vs Sea)."
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    # Permission helper properties
    @property
    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN
    
    @property
    def is_manager(self) -> bool:
        return self.role == self.ROLE_MANAGER
    
    @property
    def is_finance(self) -> bool:
        return self.role == self.ROLE_FINANCE
    
    @property
    def is_sales(self) -> bool:
        return self.role == self.ROLE_SALES
    
    @property
    def can_view_cogs(self) -> bool:
        """Manager, Finance, and Admin can view COGS/buy rates."""
        return self.role in [self.ROLE_MANAGER, self.ROLE_FINANCE, self.ROLE_ADMIN]
    
    @property
    def can_view_margins(self) -> bool:
        """Manager, Finance, and Admin can view margins."""
        return self.role in [self.ROLE_MANAGER, self.ROLE_FINANCE, self.ROLE_ADMIN]
    
    @property
    def can_edit_quotes(self) -> bool:
        """Sales, Manager, and Admin can create/edit quotes."""
        return self.role in [self.ROLE_SALES, self.ROLE_MANAGER, self.ROLE_ADMIN]
    
    @property
    def can_finalize_quotes(self) -> bool:
        """Sales, Manager, and Admin can finalize quotes."""
        return self.role in [self.ROLE_SALES, self.ROLE_MANAGER, self.ROLE_ADMIN]
    
    @property
    def can_edit_rate_cards(self) -> bool:
        """Manager and Admin can edit rate cards."""
        return self.role in [self.ROLE_MANAGER, self.ROLE_ADMIN]
    
    @property
    def can_edit_fx_rates(self) -> bool:
        """Finance and Admin can edit FX rates."""
        return self.role in [self.ROLE_FINANCE, self.ROLE_ADMIN]
    
    @property
    def can_use_ai_intake(self) -> bool:
        """Sales, Manager, and Admin can use AI-assisted rate intake."""
        return self.role in [self.ROLE_SALES, self.ROLE_MANAGER, self.ROLE_ADMIN]
    
    @property
    def can_manage_users(self) -> bool:
        """Manager and Admin can manage users."""
        return self.role in [self.ROLE_MANAGER, self.ROLE_ADMIN]
    
    @property
    def can_access_system_settings(self) -> bool:
        """Only Admin can access system settings."""
        return self.role == self.ROLE_ADMIN
    
    @property
    def can_view_audit_logs(self) -> bool:
        """Manager, Finance, and Admin can view audit logs."""
        return self.role in [self.ROLE_MANAGER, self.ROLE_FINANCE, self.ROLE_ADMIN]