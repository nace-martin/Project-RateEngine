from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db.models import QuerySet
from quotes.models import Quote

def get_quote_for_user(user, quote_id: str, queryset: QuerySet | None = None) -> Quote:
    """
    Retrieve a quote by ID while strictly enforcing RBAC ownership and location rules.
    
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
    from accounts.access_control import can_user_view_quote
    if not user or not user.is_authenticated:
         raise PermissionDenied("Authentication required.")

    if not can_user_view_quote(user, quote):
        raise PermissionDenied("You do not have permission to access this quote.")
        
    return quote
