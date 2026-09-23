"""
Commercial Terms Policy Resolution Service.

Provides deterministic resolution of CommercialTermsPolicy for pricing calculations.
Replaces legacy core.Policy as the active commercial terms calculation authority (Wave 3B2).
"""

import logging
from datetime import date, datetime

from django.db.models import Q
from django.utils import timezone

from pricing_v4.commercial_models import CommercialTermsPolicy

logger = logging.getLogger(__name__)


class MissingCommercialPolicyError(ValueError):
    """Raised when an active CommercialTermsPolicy is required but not found."""


def resolve_commercial_terms_policy(
    effective_date: date | datetime | str | None = None,
) -> CommercialTermsPolicy | None:
    """
    Resolve the authoritative CommercialTermsPolicy for a given effective date.

    Deterministic resolution rules:
    1. Filter for active policies (is_active=True).
    2. Normalize effective_date to date (defaults to current date if None).
    3. Match valid_from <= target_date AND (valid_until IS NULL OR valid_until >= target_date).
    4. Order by -valid_from.
    5. Return the single best-matching policy, or None if no valid active policy exists.
    """
    target_date: date
    if effective_date is not None:
        if isinstance(effective_date, str):
            clean_str = effective_date.strip().split("T")[0].split(" ")[0]
            try:
                target_date = date.fromisoformat(clean_str)
            except ValueError:
                logger.warning("Invalid effective_date string '%s'; falling back to current date.", effective_date)
                target_date = timezone.now().date()
        elif isinstance(effective_date, datetime):
            target_date = effective_date.date()
        elif isinstance(effective_date, date):
            target_date = effective_date
        else:
            target_date = timezone.now().date()
    else:
        target_date = timezone.now().date()

    return CommercialTermsPolicy.objects.filter(
        is_active=True,
        valid_from__lte=target_date,
    ).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=target_date)
    ).order_by("-valid_from").first()


def require_commercial_terms_policy(
    effective_date: date | datetime | str | None = None,
) -> CommercialTermsPolicy:
    """
    Resolve the authoritative CommercialTermsPolicy or fail closed with MissingCommercialPolicyError.
    """
    policy = resolve_commercial_terms_policy(effective_date)
    if policy is None:
        raise MissingCommercialPolicyError(
            f"No active CommercialTermsPolicy found for effective date '{effective_date}'. "
            "Calculation fails closed."
        )
    return policy
