from rest_framework import permissions

class IsSales(permissions.BasePermission):
    """
    Custom permission to only allow sales users to perform certain actions.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'sales'

class IsManager(permissions.BasePermission):
    """
    Custom permission to only allow manager users to perform certain actions.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'manager'

class IsFinance(permissions.BasePermission):
    """
    Custom permission to only allow finance users to perform certain actions.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'finance'

class IsManagerOrFinance(permissions.BasePermission):
    """
    Custom permission to only allow manager or finance users to perform certain actions.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['manager', 'finance']

class CanViewCOGS(permissions.BasePermission):
    """
    Custom permission to allow only manager and finance users to view COGS data.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['manager', 'finance']

class CanModifyPricingRules(permissions.BasePermission):
    """
    Custom permission to allow only finance users to modify pricing rules.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'finance'