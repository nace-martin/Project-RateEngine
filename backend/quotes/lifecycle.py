"""
Derived quote lifecycle evaluation.

Quote.status records the user's workflow state. Rate completeness, SPOT need,
and action eligibility are derived here from persisted quote calculation data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from quotes.completeness import ALL_COMPONENTS, evaluate_from_lines
from quotes.models import Quote


STATUS_READY = "READY"
STATUS_SPOT_REQUIRED = "SPOT_REQUIRED"
STATUS_MISSING_RATES = "MISSING_RATES"


@dataclass(frozen=True)
class QuoteLifecycleResult:
    status_recommendation: str
    missing_components: list[str]
    requires_spot: bool
    can_finalize: bool
    can_delete: bool
    validation_errors: list[str]
    component_outcomes: dict[str, dict[str, bool]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QuoteLifecycleService:
    """Single lifecycle evaluator for standard and SPOT-created quotes."""

    FINALIZED_OR_LOCKED_STATUSES = {
        Quote.Status.FINALIZED,
        Quote.Status.SENT,
        Quote.Status.ACCEPTED,
        Quote.Status.LOST,
        Quote.Status.EXPIRED,
    }

    @classmethod
    def evaluate(cls, quote: Quote) -> QuoteLifecycleResult:
        latest_version = getattr(quote, "latest_version", None)
        if latest_version is None and quote.pk:
            latest_version = quote.versions.order_by("-version_number").first()

        validation_errors: list[str] = []
        if getattr(quote, "is_archived", False):
            validation_errors.append("Quote is archived.")

        coverage = None
        missing_components: list[str] = []
        if latest_version is None:
            validation_errors.append("Quote has no computed version data.")
            component_outcomes = {
                component: {
                    "required": False,
                    "covered": False,
                    "missing": False,
                }
                for component in sorted(ALL_COMPONENTS)
            }
        else:
            lines = latest_version.lines.all()
            coverage = evaluate_from_lines(
                lines,
                shipment_type=quote.shipment_type,
                service_scope=quote.service_scope,
            )
            missing_components = sorted(coverage.missing_required)
            component_outcomes = {
                component: {
                    "required": component in coverage.required_components,
                    "covered": bool(coverage.component_coverage.get(component, False)),
                    "missing": component in coverage.missing_required,
                }
                for component in sorted(ALL_COMPONENTS)
            }

        is_locked = (
            quote.status in cls.FINALIZED_OR_LOCKED_STATUSES
            or bool(getattr(quote, "finalized_at", None))
        )
        requires_spot = bool(missing_components)
        can_finalize = (
            quote.status == Quote.Status.DRAFT
            and not is_locked
            and latest_version is not None
            and not validation_errors
            and not missing_components
        )
        can_delete = (
            quote.status == Quote.Status.DRAFT
            and not is_locked
            and not getattr(quote, "is_archived", False)
        )

        if is_locked:
            status_recommendation = Quote.Status.FINALIZED
        elif requires_spot:
            status_recommendation = STATUS_SPOT_REQUIRED
        elif can_finalize:
            status_recommendation = STATUS_READY
        elif missing_components:
            status_recommendation = STATUS_MISSING_RATES
        else:
            status_recommendation = Quote.Status.DRAFT

        return QuoteLifecycleResult(
            status_recommendation=status_recommendation,
            missing_components=missing_components,
            requires_spot=requires_spot,
            can_finalize=can_finalize,
            can_delete=can_delete,
            validation_errors=validation_errors,
            component_outcomes=component_outcomes,
        )
