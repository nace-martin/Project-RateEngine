# backend/accounts/permissions.py
"""
Role-Based Access Control (RBAC) permission classes for Django REST Framework.

These permissions enforce server-side access control based on user roles.
Frontend UI hiding is secondary - these permissions are the authoritative source.

Role Permission Matrix:
| Feature                 | Sales | Manager | Finance | Admin |
|-------------------------|-------|---------|---------|-------|
| View Quotes             | ✅    | ✅      | ✅      | ✅    |
| Create/Edit Quotes      | ✅    | ✅      | ❌      | ✅    |
| Finalize Quotes         | ✅    | ✅      | ❌      | ✅    |
| View COGS/Buy Rates     | ❌    | ✅      | ✅      | ✅    |
| View Margins            | ❌    | ✅      | ✅      | ✅    |
| Edit Rate Cards         | ❌    | ✅      | ❌      | ✅    |
| Edit FX Rates           | ❌    | ❌      | ✅      | ✅    |
| AI-Assisted Rate Intake | ✅    | ✅      | ❌      | ✅    |
| User Management         | ❌    | ✅      | ❌      | ✅    |
| System Settings         | ❌    | ❌      | ❌      | ✅    |
| View Audit Logs         | ❌    | ✅      | ✅      | ✅    |
"""

from rest_framework.permissions import BasePermission
from .models import CustomUser


class IsAdmin(BasePermission):
    """
    Allows access only to Admin users.
    Admin has full system access.
    """
    message = "Admin access required."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == CustomUser.ROLE_ADMIN
        )


class IsManagerOrAdmin(BasePermission):
    """
    Allows access to Manager and Admin users.
    Used for: Rate card management, User management
    """
    message = "Manager or Admin access required."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [CustomUser.ROLE_MANAGER, CustomUser.ROLE_ADMIN]
        )


class IsFinanceOrAdmin(BasePermission):
    """
    Allows access to Finance and Admin users.
    Used for: FX rate management
    """
    message = "Finance or Admin access required."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [CustomUser.ROLE_FINANCE, CustomUser.ROLE_ADMIN]
        )


class CanViewCOGS(BasePermission):
    """
    Allows access to users who can view COGS/buy rates.
    Excludes: Sales
    Includes: Manager, Finance, Admin
    """
    message = "You do not have permission to view cost data."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_view_cogs
        )


class CanEditQuotes(BasePermission):
    """
    Allows access to users who can create/edit quotes.
    Includes: Sales, Manager, Admin
    Excludes: Finance
    """
    message = "You do not have permission to edit quotes."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_edit_quotes
        )


class CanFinalizeQuotes(BasePermission):
    """
    Allows access to users who can finalize quotes.
    Includes: Sales, Manager, Admin
    Excludes: Finance
    """
    message = "You do not have permission to finalize quotes."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_finalize_quotes
        )


class CanEditRateCards(BasePermission):
    """
    Allows access to users who can edit rate cards.
    Includes: Manager, Admin
    Excludes: Sales, Finance
    """
    message = "You do not have permission to edit rate cards."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_edit_rate_cards
        )


class CanEditFXRates(BasePermission):
    """
    Allows access to users who can edit FX rates.
    Includes: Finance, Admin
    Excludes: Sales, Manager
    """
    message = "You do not have permission to edit FX rates."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_edit_fx_rates
        )


class CanUseAIIntake(BasePermission):
    """
    Allows access to users who can use AI-assisted rate intake.
    Includes: Sales, Manager, Admin
    Excludes: Finance
    """
    message = "You do not have permission to use AI rate intake."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_use_ai_intake
        )


class CanManageUsers(BasePermission):
    """
    Allows access to users who can manage other users.
    Includes: Manager, Admin
    Excludes: Sales, Finance
    """
    message = "You do not have permission to manage users."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_manage_users
        )


class CanAccessSystemSettings(BasePermission):
    """
    Allows access only to Admin for system settings.
    """
    message = "Admin access required for system settings."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_access_system_settings
        )


class CanViewAuditLogs(BasePermission):
    """
    Allows access to users who can view audit logs.
    Includes: Manager, Finance, Admin
    Excludes: Sales
    """
    message = "You do not have permission to view audit logs."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.can_view_audit_logs
        )


class QuoteAccessPermission(BasePermission):
    """
    Smart permission for quote access:
    - All authenticated users can VIEW quotes
    - Only Sales, Manager, Admin can CREATE/EDIT quotes
    """
    message = "You do not have permission to modify quotes."
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # All roles can read quotes
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # For write methods, check edit permission
        return request.user.can_edit_quotes