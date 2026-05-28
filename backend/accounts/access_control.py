# backend/accounts/access_control.py
"""
Central Access Control Service for RateEngine.
Implements the Phase 1 RBAC and Location Access rules.
"""

from django.db.models import Q
from django.conf import settings
from core.models import Location
from .models import CustomUser

def get_user_allowed_departments(user) -> list[str]:
    """
    Returns the list of department codes the user is authorized to access.
    Django superuser or admin role gets all departments.
    If a user has no primary department and no allowed departments:
    - If settings.RBAC_COMPAT_MODE is True, we return all departments to maintain backwards compatibility.
    - Otherwise, we return an empty list (fail-closed boundary for unassigned real production users).
    """
    if not user or not user.is_authenticated:
        return []
        
    all_depts = ['AIR', 'SEA', 'LAND', 'CUSTOMS']
    if user.is_superuser or getattr(user, 'role', '') == CustomUser.ROLE_ADMIN:
        return all_depts
        
    allowed = []
    primary_dept = getattr(user, 'department', None)
    if primary_dept:
        allowed.append(primary_dept.upper())
        
    # Additional allowed departments from JSONField
    additional_depts = getattr(user, 'allowed_departments', [])
    if isinstance(additional_depts, list):
        for dept in additional_depts:
            dept_upper = str(dept).upper()
            if dept_upper not in allowed:
                allowed.append(dept_upper)
                
    if not allowed:
        if getattr(settings, 'RBAC_COMPAT_MODE', False):
            # Backwards compatibility: unassigned users can access all departments in tests
            return all_depts
        # Production strict fail-closed
        return []
        
    return allowed

def get_user_allowed_locations(user) -> Q | None:
    """
    Returns the queryset Q object of locations the user is authorized to access,
    or None if the user has unrestricted global access (Admin/Superuser/Compatibility).
    """
    if not user or not user.is_authenticated:
        return Q(id__in=[])  # Empty Q matching nothing
        
    if user.is_superuser or getattr(user, 'role', '') == CustomUser.ROLE_ADMIN:
        return None  # Unrestricted access
        
    # Collect primary and other authorized locations
    loc_ids = []
    if getattr(user, 'primary_location', None):
        loc_ids.append(user.primary_location.id)
        
    auth_locs = user.authorised_locations.all()
    for loc in auth_locs:
        if loc.id not in loc_ids:
            loc_ids.append(loc.id)
            
    if not loc_ids:
        if getattr(settings, 'RBAC_COMPAT_MODE', False):
            # Backwards compatibility: unassigned users have unrestricted location access in tests
            return None
        # Production strict fail-closed
        return Q(id__in=[])
        
    return Q(id__in=loc_ids)

def get_user_allowed_location_codes(user) -> set[str]:
    """
    Returns a set of 3-letter uppercase location codes the user is authorized to access,
    or a set containing '*' if unrestricted (Admin/Superuser/Compatibility).
    """
    if not user or not user.is_authenticated:
        return set()
        
    if user.is_superuser or getattr(user, 'role', '') == CustomUser.ROLE_ADMIN:
        return {'*'}
        
    codes = set()
    if getattr(user, 'primary_location', None):
        codes.add(user.primary_location.code.upper())
        
    auth_locs = user.authorised_locations.all()
    for loc in auth_locs:
        codes.add(loc.code.upper())
        
    if not codes:
        if getattr(settings, 'RBAC_COMPAT_MODE', False):
            # Backwards compatibility: unassigned users have unrestricted location access in tests
            return {'*'}
        # Production strict fail-closed
        return set()
        
    return codes

def can_user_view_quote(user, quote) -> bool:
    """
    Determines if a user has read visibility for a given quote.
    """
    if not user or not user.is_authenticated:
        return False
        
    # Django superuser or Admin role bypass
    if user.is_superuser or getattr(user, 'role', '') == CustomUser.ROLE_ADMIN:
        return True
        
    # Finance role has global read-only visibility
    role = getattr(user, 'role', '')
    if role == CustomUser.ROLE_FINANCE:
        return True
        
    # 1. Department Enforcement
    user_dept = getattr(user, 'department', None)
    if user_dept:
        allowed_depts = get_user_allowed_departments(user)
        quote_mode = getattr(quote, 'mode', 'AIR').upper()
        if quote_mode not in allowed_depts:
            return False
    else:
        # Fallback: Manager with no department sees only their own quotes
        if role == CustomUser.ROLE_MANAGER and quote.created_by != user:
            return False
        
    # 2. Location Enforcement
    allowed_codes = get_user_allowed_location_codes(user)
    if '*' not in allowed_codes:
        # Determine the managing branch for the quote
        quote_branch_code = None
        if getattr(quote, 'owning_location', None):
            quote_branch_code = quote.owning_location.code.upper()
        elif getattr(quote, 'origin_location', None):
            quote_branch_code = quote.origin_location.code.upper()
        elif getattr(quote, 'destination_location', None):
            quote_branch_code = quote.destination_location.code.upper()
            
        if not quote_branch_code or quote_branch_code not in allowed_codes:
            return False
            
    # 3. Role / Ownership Enforcement
    if role == CustomUser.ROLE_MANAGER:
        return True  # Managers can see all quotes in their allowed dept + location scope
        
    # Sales can only see their own quotes within allowed scope
    return quote.created_by == user

def can_user_edit_quote(user, quote) -> bool:
    """
    Determines if a user has write/edit/delete/clone permission for a given quote.
    """
    if not user or not user.is_authenticated:
        return False
        
    # Only Sales, Manager, and Admin can edit quotes
    role = getattr(user, 'role', '')
    if role not in [CustomUser.ROLE_SALES, CustomUser.ROLE_MANAGER, CustomUser.ROLE_ADMIN] and not user.is_superuser:
        return False
        
    # Django superuser or Admin role bypass
    if user.is_superuser or role == CustomUser.ROLE_ADMIN:
        return True
        
    # 1. Department Enforcement
    user_dept = getattr(user, 'department', None)
    if user_dept:
        allowed_depts = get_user_allowed_departments(user)
        quote_mode = getattr(quote, 'mode', 'AIR').upper()
        if quote_mode not in allowed_depts:
            return False
    else:
        # Fallback: Manager with no department edits only their own quotes
        if role == CustomUser.ROLE_MANAGER and quote.created_by != user:
            return False
        
    # 2. Location Enforcement
    allowed_codes = get_user_allowed_location_codes(user)
    if '*' not in allowed_codes:
        # Determine the managing branch for the quote
        quote_branch_code = None
        if getattr(quote, 'owning_location', None):
            quote_branch_code = quote.owning_location.code.upper()
        elif getattr(quote, 'origin_location', None):
            quote_branch_code = quote.origin_location.code.upper()
        elif getattr(quote, 'destination_location', None):
            quote_branch_code = quote.destination_location.code.upper()
            
        if not quote_branch_code or quote_branch_code not in allowed_codes:
            return False
            
    # 3. Ownership Enforcement
    if role == CustomUser.ROLE_MANAGER:
        return True  # Managers can edit all quotes in their allowed dept + location scope
        
    # Sales can only edit their own quotes
    return quote.created_by == user

def get_quote_queryset_filter(user) -> Q:
    """
    Generates a Django Q object representing the filtering rules for the Quote model.
    """
    if not user or not user.is_authenticated:
        return Q(id__in=[])  # Match nothing
        
    # Admin/Superuser or Finance gets all quotes
    role = getattr(user, 'role', '')
    if user.is_superuser or role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_FINANCE]:
        return Q()
        
    base_filter = Q()
    
    # 1. Filter by allowed departments
    user_dept = getattr(user, 'department', None)
    if user_dept:
        allowed_depts = get_user_allowed_departments(user)
        base_filter &= Q(mode__in=allowed_depts)
    else:
        # Fallback: Manager with no department sees only their own quotes
        if role == CustomUser.ROLE_MANAGER:
            base_filter &= Q(created_by=user)
    
    # 2. Filter by allowed locations
    allowed_codes = get_user_allowed_location_codes(user)
    if '*' not in allowed_codes:
        # Match quote's owning_location or fallback to origin/destination locations
        location_filter = (
            Q(owning_location__code__in=allowed_codes) |
            Q(owning_location__isnull=True, origin_location__code__in=allowed_codes) |
            Q(owning_location__isnull=True, destination_location__code__in=allowed_codes)
        )
        base_filter &= location_filter
        
    # 3. Filter by Sales ownership restriction
    if role == CustomUser.ROLE_SALES:
        base_filter &= Q(created_by=user)
        
    return base_filter
