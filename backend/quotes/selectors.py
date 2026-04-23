from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404

from quotes.models import Quote


def get_quotes_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    """
    Apply the strict-by-default quote visibility policy.

    Rules:
    - Admin/Finance: global access.
    - Managers: same-department quotes plus own quotes.
    - Managers without a valid department: own quotes only.
    - Sales/standard users: own quotes only.
    """
    if queryset is None:
        queryset = Quote.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    role = getattr(user, "role", "")
    is_global = (
        getattr(user, "is_admin", False)
        or getattr(user, "is_finance", False)
        or role in ("admin", "finance")
    )
    if is_global:
        return queryset

    is_manager = getattr(user, "is_manager", False) or role == "manager"
    valid_departments = getattr(type(user), "valid_departments", lambda: set())()
    user_department = getattr(user, "department", None)

    if is_manager:
        if user_department and user_department in valid_departments:
            return queryset.filter(
                Q(created_by__department=user_department) | Q(created_by=user)
            )
        return queryset.filter(created_by=user)

    return queryset.filter(created_by=user)


def get_quote_for_user(user, quote_id: str, queryset: QuerySet | None = None) -> Quote:
    """
    Retrieve a quote by ID while enforcing the shared selector policy.
    """
    if queryset is None:
        queryset = Quote.objects.all()

    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    try:
        return get_quotes_for_user(user, queryset).get(id=quote_id)
    except Quote.DoesNotExist as exc:
        raise Http404("No Quote matches the given query.") from exc
