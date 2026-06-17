from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet

from accounts.models import CustomUser
from accounts.scope import get_active_memberships, get_effective_user_scope
from quotes.models import Quote
from quotes.selectors import get_quotes_for_user, get_spes_for_user
from quotes.spot_models import SpotPricingEnvelopeDB


@dataclass(frozen=True)
class SelectorComparison:
    legacy_ids: frozenset
    scope_ids: frozenset
    only_legacy_ids: frozenset
    only_scope_ids: frozenset

    @property
    def has_mismatch(self) -> bool:
        return bool(self.only_legacy_ids or self.only_scope_ids)


def compare_quote_visibility(user, queryset: QuerySet | None = None) -> SelectorComparison:
    if queryset is None:
        queryset = Quote.objects.all()

    legacy_ids = frozenset(get_quotes_for_user(user, queryset).values_list("id", flat=True))
    scope_ids = frozenset(
        _get_records_for_scope(user, queryset, legacy_selector=get_quotes_for_user).values_list(
            "id",
            flat=True,
        )
    )
    return _build_comparison(legacy_ids, scope_ids)


def compare_spe_visibility(user, queryset: QuerySet | None = None) -> SelectorComparison:
    if queryset is None:
        queryset = SpotPricingEnvelopeDB.objects.all()

    legacy_ids = frozenset(get_spes_for_user(user, queryset).values_list("id", flat=True))
    scope_ids = frozenset(
        _get_records_for_scope(user, queryset, legacy_selector=get_spes_for_user).values_list(
            "id",
            flat=True,
        )
    )
    return _build_comparison(legacy_ids, scope_ids)


def _build_comparison(legacy_ids: frozenset, scope_ids: frozenset) -> SelectorComparison:
    return SelectorComparison(
        legacy_ids=legacy_ids,
        scope_ids=scope_ids,
        only_legacy_ids=frozenset(legacy_ids - scope_ids),
        only_scope_ids=frozenset(scope_ids - legacy_ids),
    )


def _get_records_for_scope(user, queryset: QuerySet, *, legacy_selector) -> QuerySet:
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    if not getattr(user, "is_active", False):
        return queryset.none()

    memberships = list(get_active_memberships(user))
    if not memberships:
        return legacy_selector(user, queryset)

    scope = get_effective_user_scope(user)
    role_codes = scope.role_codes

    if role_codes.intersection({CustomUser.ROLE_ADMIN, CustomUser.ROLE_FINANCE}):
        return queryset

    if CustomUser.ROLE_MANAGER in role_codes:
        department_ids = scope.department_ids
        if department_ids:
            return queryset.filter(
                Q(created_by=user)
                | Q(
                    created_by__memberships__is_active=True,
                    created_by__memberships__department_id__in=department_ids,
                )
            ).distinct()
        return queryset.filter(created_by=user)

    return queryset.filter(created_by=user)
