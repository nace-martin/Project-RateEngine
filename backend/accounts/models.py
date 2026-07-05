# backend/accounts/models.py

from django.conf import settings
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
    can_view_buy_charges_override = models.BooleanField(
        default=False, 
        help_text="Explicitly allow viewing buy cost data regardless of role."
    )
    can_view_margins_override = models.BooleanField(
        default=False, 
        help_text="Explicitly allow viewing margins regardless of role."
    )

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
    organization = models.ForeignKey(
        'parties.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
        help_text="Tenant/account workspace this user belongs to.",
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
    def can_view_buy_charges(self) -> bool:
        """Effective check: all authenticated roles can view buy cost data by default."""
        return True

    @property
    def can_view_cogs(self) -> bool:
        """Alias for can_view_buy_charges to maintain compatibility with legacy checks."""
        return self.can_view_buy_charges
    
    @property
    def can_view_margins(self) -> bool:
        """Effective check: Manager, Finance, and Admin can view margins. Sales requires override."""
        role_allows = self.role in [self.ROLE_MANAGER, self.ROLE_FINANCE, self.ROLE_ADMIN]
        return role_allows or self.can_view_margins_override
    
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
    def can_use_spot_workspace(self) -> bool:
        """Sales, Manager, and Admin can use the SPOT workspace."""
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


class Permission(models.Model):
    """
    Stable permission code for future RBAC checks.

    This is seeded and stored now, but existing behavior remains driven by the
    compatibility helpers on CustomUser until later phases wire it in.
    """

    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    """
    Role template or organization-specific role for RBAC foundations.

    organization=None represents the system template roles that mirror current
    CustomUser.role values.
    """

    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    organization = models.ForeignKey(
        "parties.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="roles",
    )
    is_system = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    permissions = models.ManyToManyField(
        Permission,
        through="RolePermission",
        related_name="roles",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization__name", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_role_code_per_organization",
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(organization__isnull=True),
                name="unique_system_role_code",
            ),
        ]

    def __str__(self):
        scope = self.organization.slug if self.organization_id else "system"
        return f"{scope}:{self.code}"


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role__code", "permission__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="unique_role_permission",
            ),
        ]

    def __str__(self):
        return f"{self.role} -> {self.permission.code}"


class UserMembership(models.Model):
    """
    User membership in an organization/branch/department with an RBAC role.

    branch and department are nullable for compatibility with existing users.
    These memberships are seeded now but are not used for enforcement yet.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        "parties.Organization",
        on_delete=models.CASCADE,
        related_name="user_memberships",
    )
    operating_entity = models.ForeignKey(
        "parties.OperatingEntity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_memberships",
    )
    branch = models.ForeignKey(
        "parties.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_memberships",
    )
    department = models.ForeignKey(
        "parties.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_memberships",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="user_memberships",
    )
    is_primary = models.BooleanField(default=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "organization__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_primary=True, is_active=True),
                name="unique_active_primary_membership_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization}"
