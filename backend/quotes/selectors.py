from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db.models import QuerySet, Q
from quotes.models import Quote, SpotPricingEnvelopeDB

def get_spes_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    """
    Apply departmental and role-based visibility filters to a SpotPricingEnvelopeDB queryset.

    Rules:
    - Admin/Finance: Global access.
    - Managers: Own department's SPEs + own SPEs.
    - Sales: Own SPEs only.
    """
    if queryset is None:
        queryset = SpotPricingEnvelopeDB.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    role = getattr(user, 'role', '')
    is_global = (
        getattr(user, 'is_admin', False) or
        getattr(user, 'is_finance', False) or
        role in ('admin', 'finance')
    )

    if is_global:
        return queryset

    # Manager View: Restricted by Department
    if getattr(user, 'is_manager', False) or role == 'manager':
        dept = getattr(user, 'department', None)
        if dept:
            return queryset.filter(
                Q(created_by__department=dept) |
                Q(created_by=user)
            )
        return queryset.filter(created_by=user)

    # Sales / Standard View: Own SPEs only
    return queryset.filter(created_by=user)


def get_quotes_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    """
    Apply departmental and role-based visibility filters to a Quote queryset.

    Rules:
    - Admin/Finance: Global access.
    - Managers: Own department's quotes + own quotes.
    - Sales: Own quotes only.
    """
    if queryset is None:
        queryset = Quote.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    role = getattr(user, 'role', '')
    is_global = (
        getattr(user, 'is_admin', False) or
        getattr(user, 'is_finance', False) or
        role in ('admin', 'finance')
    )

    if is_global:
        return queryset

    # Manager View: Restricted by Department
    if getattr(user, 'is_manager', False) or role == 'manager':
        dept = getattr(user, 'department', None)
        if dept:
            return queryset.filter(
                Q(created_by__department=dept) |
                Q(created_by=user)
            )
        return queryset.filter(created_by=user)

    # Sales / Standard View: Own quotes only
    return queryset.filter(created_by=user)


def get_quote_for_user(user, quote_id: str, queryset: QuerySet | None = None) -> Quote:
    """
    Retrieve a quote by ID while strictly enforcing RBAC ownership rules.
    
    Rules:
    - Manager/Admin/Finance: Can access ALL quotes (Managers restricted by department).
    - Sales: Can ONLY access quotes strictly created by themselves.
    
    Args:
        user: The requesting User object.
        quote_id: The UUID of the quote.
        queryset: Optional base queryset (e.g., used for prefetching).
        
    Returns:
        Quote object.
        
    Raises:
        Http404: If quote doesn't exist or user is not allowed to access this quote.
        PermissionDenied: If user is not authenticated.
    """
    if queryset is None:
        queryset = Quote.objects.all()
        
    if not user or not user.is_authenticated:
         raise PermissionDenied("Authentication required.")

    # Use the shared filter logic
    accessible_qs = get_quotes_for_user(user, queryset)
    
    try:
        return accessible_qs.get(id=quote_id)
    except Quote.DoesNotExist:
        # We differentiate 404 vs 403 by checking if it exists at all
        # To avoid leaking existence, we raise 404 in both cases where access is denied.
        from django.http import Http404
        raise Http404("No Quote matches the given query.")
