import json

from django.core.management.base import BaseCommand, CommandError

from accounts.scope import get_active_memberships
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


STATUS_ALREADY_SCOPED = "already_scoped"
STATUS_SINGLE_MEMBERSHIP = "single_membership"
STATUS_LEGACY_FALLBACK = "legacy_fallback"
STATUS_AMBIGUOUS = "ambiguous_membership"
STATUS_UNKNOWN = "unknown"


class Command(BaseCommand):
    help = "Dry-run report for future Quote/SPE RBAC scope field backfill."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )
        parser.add_argument(
            "--model",
            choices=["quote", "spot", "all"],
            default="all",
            help="Model to inspect. Defaults to all.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit records inspected per model.",
        )
        parser.add_argument(
            "--show-details",
            action="store_true",
            help="Include per-record candidate details.",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer.")

        payload = {
            "write_enabled": False,
            "models": {},
        }

        if options["model"] in {"quote", "all"}:
            payload["models"]["quote"] = inspect_quote_scope(
                limit=limit,
                show_details=options["show_details"],
            )
        if options["model"] in {"spot", "all"}:
            payload["models"]["spot"] = inspect_spot_scope(
                limit=limit,
                show_details=options["show_details"],
            )

        payload["summary"] = _combined_summary(payload["models"])

        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self._write_text(payload, show_details=options["show_details"])

    def _write_text(self, payload: dict, *, show_details: bool):
        self.stdout.write("RBAC scope backfill dry-run report")
        self.stdout.write("==================================")
        self.stdout.write("Mode: read-only")
        self.stdout.write(
            "Combined totals: "
            f"total={payload['summary']['total_records']}, "
            f"already_scoped={payload['summary']['already_scoped']}, "
            f"single_membership={payload['summary']['single_membership_candidates']}, "
            f"legacy_fallback={payload['summary']['legacy_fallback_candidates']}, "
            f"ambiguous={payload['summary']['ambiguous_membership_candidates']}, "
            f"unknown={payload['summary']['unknown_candidates']}"
        )

        for model_name, model_payload in payload["models"].items():
            summary = model_payload["summary"]
            self.stdout.write("")
            self.stdout.write(f"{model_name}:")
            self.stdout.write(
                f"  total={summary['total_records']}, "
                f"already_scoped={summary['already_scoped']}, "
                f"single_membership={summary['single_membership_candidates']}, "
                f"legacy_fallback={summary['legacy_fallback_candidates']}, "
                f"ambiguous={summary['ambiguous_membership_candidates']}, "
                f"unknown={summary['unknown_candidates']}"
            )
            if show_details:
                for detail in model_payload["details"]:
                    self.stdout.write(
                        f"  - {detail['id']}: status={detail['status']}, "
                        f"created_by={detail['created_by_username']}"
                    )


def inspect_quote_scope(*, limit: int | None = None, show_details: bool = False) -> dict:
    queryset = Quote.objects.select_related(
        "organization",
        "branch",
        "department",
        "owner",
        "created_by",
        "created_by__organization",
    ).order_by("created_at", "id")
    if limit is not None:
        queryset = queryset[:limit]
    return _inspect_records(queryset, model_name="quote", show_details=show_details)


def inspect_spot_scope(*, limit: int | None = None, show_details: bool = False) -> dict:
    queryset = SpotPricingEnvelopeDB.objects.select_related(
        "organization",
        "branch",
        "department",
        "owner",
        "created_by",
        "created_by__organization",
    ).order_by("created_at", "id")
    if limit is not None:
        queryset = queryset[:limit]
    return _inspect_records(queryset, model_name="spot", show_details=show_details)


def _inspect_records(queryset, *, model_name: str, show_details: bool) -> dict:
    details = []
    summary = _empty_summary()

    for record in queryset:
        detail = _inspect_record(record, model_name=model_name, show_details=show_details)
        summary["total_records"] += 1
        _increment_summary(summary, detail["status"])
        if show_details:
            details.append(detail)

    payload = {"summary": summary}
    if show_details:
        payload["details"] = details
    return payload


def _inspect_record(record, *, model_name: str, show_details: bool) -> dict:
    created_by = getattr(record, "created_by", None)
    base = {
        "id": str(record.pk),
        "model": model_name,
        "status": None,
        "created_by_id": getattr(record, "created_by_id", None),
        "created_by_username": getattr(created_by, "username", None),
    }

    if _record_has_scope(record):
        base["status"] = STATUS_ALREADY_SCOPED
        if show_details:
            base["current_scope"] = _current_scope(record)
        return base

    if not created_by:
        base["status"] = STATUS_UNKNOWN
        base["reason"] = "missing_created_by"
        return base

    memberships = list(get_active_memberships(created_by))
    if len(memberships) == 1:
        membership = memberships[0]
        base["status"] = STATUS_SINGLE_MEMBERSHIP
        if show_details:
            base["candidate"] = _membership_candidate(membership, include_organization=True)
        return base

    if len(memberships) > 1:
        base["status"] = STATUS_AMBIGUOUS
        base["membership_count"] = len(memberships)
        if show_details:
            base["candidates"] = [
                _membership_candidate(membership, include_organization=True)
                for membership in memberships
            ]
        return base

    if getattr(created_by, "organization_id", None) or getattr(created_by, "department", None):
        base["status"] = STATUS_LEGACY_FALLBACK
        if show_details:
            base["legacy_candidate"] = {
                "organization_id": _string_or_none(getattr(created_by, "organization_id", None)),
                "organization_slug": getattr(getattr(created_by, "organization", None), "slug", None),
                "department_code": getattr(created_by, "department", None),
            }
        return base

    base["status"] = STATUS_UNKNOWN
    base["reason"] = "no_membership_or_legacy_scope"
    return base


def _record_has_scope(record) -> bool:
    return bool(
        getattr(record, "organization_id", None)
        or getattr(record, "branch_id", None)
        or getattr(record, "department_id", None)
        or getattr(record, "owner_id", None)
    )


def _current_scope(record) -> dict:
    return {
        "organization_id": _string_or_none(getattr(record, "organization_id", None)),
        "branch_id": _string_or_none(getattr(record, "branch_id", None)),
        "department_id": _string_or_none(getattr(record, "department_id", None)),
        "owner_id": getattr(record, "owner_id", None),
    }


def _membership_candidate(membership, *, include_organization: bool) -> dict:
    payload = {
        "branch_id": _string_or_none(membership.branch_id),
        "branch_code": getattr(getattr(membership, "branch", None), "code", None),
        "department_id": _string_or_none(membership.department_id),
        "department_code": getattr(getattr(membership, "department", None), "code", None),
        "owner_id": membership.user_id,
        "role": getattr(getattr(membership, "role", None), "code", None),
    }
    if include_organization:
        payload["organization_id"] = _string_or_none(membership.organization_id)
        payload["organization_slug"] = getattr(getattr(membership, "organization", None), "slug", None)
    return payload


def _empty_summary() -> dict:
    return {
        "total_records": 0,
        "already_scoped": 0,
        "single_membership_candidates": 0,
        "legacy_fallback_candidates": 0,
        "ambiguous_membership_candidates": 0,
        "unknown_candidates": 0,
    }


def _increment_summary(summary: dict, status: str):
    if status == STATUS_ALREADY_SCOPED:
        summary["already_scoped"] += 1
    elif status == STATUS_SINGLE_MEMBERSHIP:
        summary["single_membership_candidates"] += 1
    elif status == STATUS_LEGACY_FALLBACK:
        summary["legacy_fallback_candidates"] += 1
    elif status == STATUS_AMBIGUOUS:
        summary["ambiguous_membership_candidates"] += 1
    elif status == STATUS_UNKNOWN:
        summary["unknown_candidates"] += 1


def _combined_summary(models: dict) -> dict:
    summary = _empty_summary()
    for model_payload in models.values():
        model_summary = model_payload["summary"]
        for key in summary:
            summary[key] += model_summary[key]
    return summary


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    return str(value)
