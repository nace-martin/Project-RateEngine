from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db.models import QuerySet
from quotes.models import Quote

def get_quote_for_user(user, quote_id: str, queryset: QuerySet | None = None) -> Quote:
    """
    Retrieve a quote by ID while strictly enforcing RBAC ownership rules.
    
    Rules:
    - Manager/Admin/Finance: Can access ALL quotes.
    - Sales: Can ONLY access quotes strictly created by themselves.
    
    Args:
        user: The requesting User object.
        quote_id: The UUID of the quote.
        queryset: Optional base queryset (e.g., used for prefetching).
        
    Returns:
        Quote object.
        
    Raises:
        Http404: If quote doesn't exist.
        PermissionDenied: If user exists but is not allowed to access this quote.
    """
    if queryset is None:
        queryset = Quote.objects.all()
        
    # 1. Fetch the object independently of permission first to differentiate 404 vs 403
    quote = get_object_or_404(queryset, id=quote_id)
    
    # 2. Check Permissions
    if not user or not user.is_authenticated:
         raise PermissionDenied("Authentication required.")

    # Check for privileged roles (Global Access)
    # Only Admin (and Finance who monitors everything) get global view.
    # Managers are now restricted by department.
    role = getattr(user, 'role', '')
    is_global_admin = (
        getattr(user, 'is_admin', False) or 
        getattr(user, 'is_finance', False) or
        role in ('admin', 'finance')
    )
    
    if is_global_admin:
        return quote
        
    # Check Manager Departmental Access
    is_manager = getattr(user, 'is_manager', False) or role == 'manager'
    if is_manager:
        user_dept = getattr(user, 'department', None)
        if user_dept:
             # Check if creator is in the same department
            creator_dept = getattr(quote.created_by, 'department', None)
            if creator_dept == user_dept:
                return quote

    # 3. Creator Check (Sales / Fallback for Managers)
    # Must match created_by
    if quote.created_by_id == user.id:
        return quote
    
    # Permission Denied / 404
    from django.http import Http404
    raise Http404("No Quote matches the given query.") 
