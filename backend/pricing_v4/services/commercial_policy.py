"""
Commercial Terms Policy Resolution Service.

Provides deterministic resolution of CommercialTermsPolicy for pricing calculations.
Replaces legacy core.Policy as the active commercial terms calculation authority (Wave 3B2).
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from pricing_v4.commercial_models import CommercialTermsPolicy

logger = logging.getLogger(__name__)


class PolicyResolutionError(ValueError):
    """Base error for commercial terms policy resolution failures."""


class MissingCommercialPolicyError(PolicyResolutionError):
    """Raised when an active CommercialTermsPolicy is required but not found."""


class AmbiguousCommercialPolicyError(PolicyResolutionError):
    """Raised when more than one active CommercialTermsPolicy covers the effective date."""


class InvalidPolicyEffectiveDateError(PolicyResolutionError):
    """Raised when an invalid effective date is provided for policy resolution."""


def _normalize_effective_date(effective_date: date | datetime | str | None) -> date:
    """Normalise an effective date; invalid or unsupported input fails closed."""
    if effective_date is None:
        return timezone.now().date()
    if isinstance(effective_date, str):
        cleaned = effective_date.strip()
        if not cleaned:
            raise InvalidPolicyEffectiveDateError("Empty effective_date string provided.")
        clean_str = cleaned.split("T")[0].split(" ")[0]
        try:
            return date.fromisoformat(clean_str)
        except ValueError as err:
            raise InvalidPolicyEffectiveDateError(
                f"Invalid effective_date string '{effective_date}': {err}"
            ) from err
    if isinstance(effective_date, datetime):
        return effective_date.date()
    if isinstance(effective_date, date):
        return effective_date
    raise InvalidPolicyEffectiveDateError(
        f"Unsupported effective_date type: {type(effective_date).__name__}"
    )


def resolve_commercial_terms_policy(
    effective_date: date | datetime | str | None = None,
) -> CommercialTermsPolicy | None:
    """
    Resolve the authoritative CommercialTermsPolicy for a given effective date.

    Deterministic resolution rules:
    1. Filter for active policies (is_active=True).
    2. Normalize effective_date to date:
       - None: defaults to current date (timezone.now().date()) intentionally representing "current effective policy".
       - str: parses ISO format date string; invalid strings fail closed with InvalidPolicyEffectiveDateError.
       - datetime: extracts date component.
       - date: used directly.
       - unsupported types: fail closed with InvalidPolicyEffectiveDateError.
    3. Match valid_from <= target_date AND (valid_until IS NULL OR valid_until >= target_date).
    4. Order by -valid_from.
    5. Return the single best-matching policy, or None if no valid active policy exists.
    """
    target_date = _normalize_effective_date(effective_date)

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


def require_unique_commercial_terms_policy(
    effective_date: date | datetime | str | None = None,
) -> CommercialTermsPolicy:
    """
    Resolve the one applicable policy, failing closed on missing *and* on ambiguous.

    ``resolve_commercial_terms_policy`` keeps its long-standing "newest valid_from wins" contract for
    callers that depend on it. Commercial authority that must not guess (the GST rate) uses this.
    """
    target_date = _normalize_effective_date(effective_date)
    matches = list(
        CommercialTermsPolicy.objects.filter(is_active=True, valid_from__lte=target_date)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=target_date))
        .order_by("-valid_from", "policy_code")[:3]
    )
    if not matches:
        raise MissingCommercialPolicyError(
            f"No active CommercialTermsPolicy found for effective date '{target_date}'. Calculation fails closed."
        )
    if len(matches) > 1:
        raise AmbiguousCommercialPolicyError(
            f"More than one active CommercialTermsPolicy covers '{target_date}': "
            f"{', '.join(p.policy_code for p in matches)}. Calculation fails closed."
        )
    return matches[0]


def require_standard_gst_rate(effective_date: date | datetime | str | None = None) -> Decimal:
    """
    The standard GST rate (a fraction, e.g. ``0.10``) from the resolved commercial policy.

    This is the only runtime authority for the standard rate. A missing, ambiguous, or incomplete policy
    fails closed.
    """
    policy = require_unique_commercial_terms_policy(effective_date)
    rate = policy.gst_standard_rate
    if rate is None:
        raise MissingCommercialPolicyError(
            f"Policy {policy.policy_code} has no gst_standard_percent; calculation fails closed."
        )
    return rate
