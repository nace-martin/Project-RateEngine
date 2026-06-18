from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet, Q
from accounts.scope import get_effective_user_scope
from quotes.models import Quote, SpotPricingEnvelopeDB


def _is_global_user(user) -> bool:
    role = getattr(user, 'role', '')
    return (
        getattr(user, 'is_admin', False) or
        getattr(user, 'is_finance', False) or
        getattr(user, 'is_superuser', False) or
        role in ('admin', 'finance')
    )


def _is_manager_user(user) -> bool:
    return getattr(user, 'is_manager', False) or getattr(user, 'role', '') == 'manager'


def _legacy_manager_filter(user) -> Q:
    dept = getattr(user, 'department', None)
    if dept:
        return Q(created_by__department=dept) | Q(created_by=user)
    return Q(created_by=user)


def _manager_scoped_filter(user) -> Q:
    scope = get_effective_user_scope(user)

    scoped_filter = Q(created_by=user)
    if scope.department_ids:
        scoped_filter |= Q(department_id__in=scope.department_ids)
    if scope.branch_ids:
        scoped_filter |= Q(department_id__isnull=True, branch_id__in=scope.branch_ids)

    unscoped_filter = Q(branch_id__isnull=True, department_id__isnull=True)
    return scoped_filter | (unscoped_filter & _legacy_manager_filter(user))


def get_spes_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    """
    Apply departmental and role-based visibility filters to a SpotPricingEnvelopeDB queryset.

    Rules:
    - Admin/Finance: Global access.
    - Managers: Scoped SPEs by durable branch/department when present.
      Branch/department-unscoped SPEs keep the legacy creator department fallback.
    - Sales: Own SPEs only.
    """
    if queryset is None:
        queryset = SpotPricingEnvelopeDB.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if _is_global_user(user):
        return queryset

    if _is_manager_user(user):
        return queryset.filter(_manager_scoped_filter(user))

    # Sales / Standard View: Own SPEs only
    return queryset.filter(created_by=user)


def get_quotes_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    """
    Apply departmental and role-based visibility filters to a Quote queryset.

    Rules:
    - Admin/Finance: Global access.
    - Managers: Scoped quotes by durable branch/department when present.
      Branch/department-unscoped quotes keep the legacy creator department fallback.
    - Sales: Own quotes only.
    """
    if queryset is None:
        queryset = Quote.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if _is_global_user(user):
        return queryset

    if _is_manager_user(user):
        return queryset.filter(_manager_scoped_filter(user))

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
