import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.scope import get_active_memberships
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


SUMMARY_KEYS = (
    "total_scanned",
    "already_scoped_noop",
    "safe_candidates",
    "updated",
    "skipped_ambiguous",
    "skipped_no_membership",
    "skipped_no_created_by",
    "skipped_inactive_user",
    "skipped_existing_values",
    "errors",
)


class Command(BaseCommand):
    help = "Dry-run by default; optionally backfill Quote/SPE RBAC scope from one active membership."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Read-only mode. This is the default.")
        parser.add_argument("--write", action="store_true", help="Write safe backfill changes.")
        parser.add_argument("--model", choices=["quote", "spot", "all"], default="all")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--show-details", action="store_true")
        parser.add_argument("--only-safe-single-membership", action="store_true", default=True)
        parser.add_argument("--fill-missing-only", action="store_true", default=True)

    def handle(self, *args, **options):
        if options["write"] and options["dry_run"]:
            raise CommandError("Use either --write or --dry-run, not both.")
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be a positive integer.")

        write = bool(options["write"])
        payload = {"write_enabled": write, "models": {}}

        if options["model"] in {"quote", "all"}:
            payload["models"]["quote"] = backfill_quote_scope(
                write=write,
                limit=options["limit"],
                show_details=options["show_details"],
            )
        if options["model"] in {"spot", "all"}:
            payload["models"]["spot"] = backfill_spot_scope(
                write=write,
                limit=options["limit"],
                show_details=options["show_details"],
            )

        payload["summary"] = _combined_summary(payload["models"])
        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        _write_text(self.stdout, payload, show_details=options["show_details"])


def backfill_quote_scope(*, write: bool, limit: int | None = None, show_details: bool = False) -> dict:
    queryset = Quote.objects.select_related("created_by").order_by("created_at", "id")
    if limit is not None:
        queryset = queryset[:limit]
    return _backfill_records(
        queryset,
        model_name="quote",
        write=write,
        show_details=show_details,
        fields=("organization", "branch", "department", "owner"),
    )


def backfill_spot_scope(*, write: bool, limit: int | None = None, show_details: bool = False) -> dict:
    queryset = SpotPricingEnvelopeDB.objects.select_related("created_by").order_by("created_at", "id")
    if limit is not None:
        queryset = queryset[:limit]
    return _backfill_records(
        queryset,
        model_name="spot",
        write=write,
        show_details=show_details,
        fields=("organization", "branch", "department", "owner"),
    )


def _backfill_records(queryset, *, model_name: str, write: bool, show_details: bool, fields: tuple[str, ...]) -> dict:
    summary = _empty_summary()
    details = []

    for record in queryset:
        detail = _inspect_backfill_candidate(record, model_name=model_name, fields=fields)
        summary["total_scanned"] += 1
        summary[detail["status"]] += 1

        if write and detail["status"] == "safe_candidates":
            try:
                with transaction.atomic():
                    update_fields = _apply_missing_scope(record, detail["_candidate_values"], fields)
                    if update_fields:
                        record.save(update_fields=update_fields)
                        detail["updated_fields"] = update_fields
                        summary["updated"] += 1
                    else:
                        detail["status"] = "skipped_existing_values"
                        summary["safe_candidates"] -= 1
                        summary["skipped_existing_values"] += 1
            except Exception as exc:
                detail["status"] = "errors"
                detail["error"] = str(exc)
                summary["safe_candidates"] -= 1
                summary["errors"] += 1

        if show_details:
            detail.pop("_candidate_values", None)
            details.append(detail)

    payload = {"summary": summary}
    if show_details:
        payload["details"] = details
    return payload


def _inspect_backfill_candidate(record, *, model_name: str, fields: tuple[str, ...]) -> dict:
    created_by = getattr(record, "created_by", None)
    detail = {
        "id": str(record.pk),
        "model": model_name,
        "status": None,
        "created_by_id": getattr(record, "created_by_id", None),
        "created_by_username": getattr(created_by, "username", None),
    }

    if not created_by:
        detail["status"] = "skipped_no_created_by"
        return detail
    if not getattr(created_by, "is_active", False):
        detail["status"] = "skipped_inactive_user"
        return detail

    memberships = list(get_active_memberships(created_by))
    if not memberships:
        detail["status"] = "skipped_no_membership"
        return detail
    if len(memberships) > 1:
        detail["status"] = "skipped_ambiguous"
        detail["membership_count"] = len(memberships)
        return detail

    candidate = _candidate_from_membership(memberships[0], created_by)
    missing_fields = [
        field for field in fields
        if getattr(record, f"{field}_id", None) is None and candidate[field] is not None
    ]
    detail["candidate"] = _candidate_ids(candidate)
    detail["_candidate_values"] = candidate
    detail["missing_fields"] = missing_fields

    if missing_fields:
        detail["status"] = "safe_candidates"
        return detail

    detail["status"] = "already_scoped_noop"
    return detail


def _candidate_from_membership(membership, user) -> dict:
    return {
        "organization": membership.organization,
        "branch": membership.branch,
        "department": membership.department,
        "owner": user,
    }


def _candidate_ids(candidate: dict) -> dict:
    return {field: _string_or_none(getattr(value, "pk", None)) for field, value in candidate.items()}


def _apply_missing_scope(record, candidate: dict, fields: tuple[str, ...]) -> list[str]:
    update_fields = []
    for field in fields:
        if getattr(record, f"{field}_id", None) is None and candidate[field] is not None:
            setattr(record, field, candidate[field])
            update_fields.append(field)
    return update_fields


def _empty_summary() -> dict:
    return {key: 0 for key in SUMMARY_KEYS}


def _combined_summary(models: dict) -> dict:
    summary = _empty_summary()
    for model_payload in models.values():
        for key in summary:
            summary[key] += model_payload["summary"][key]
    return summary


def _write_text(stdout, payload: dict, *, show_details: bool):
    mode = "write" if payload["write_enabled"] else "dry-run"
    stdout.write("RBAC scope backfill")
    stdout.write("===================")
    stdout.write(f"Mode: {mode}")
    stdout.write(_summary_line("Combined totals", payload["summary"]))
    for model_name, model_payload in payload["models"].items():
        stdout.write("")
        stdout.write(f"{model_name}:")
        stdout.write(_summary_line("  totals", model_payload["summary"]))
        if show_details:
            for detail in model_payload["details"]:
                stdout.write(
                    f"  - {detail['id']}: status={detail['status']}, "
                    f"created_by={detail['created_by_username']}"
                )


def _summary_line(label: str, summary: dict) -> str:
    return (
        f"{label}: scanned={summary['total_scanned']}, "
        f"safe={summary['safe_candidates']}, updated={summary['updated']}, "
        f"already_scoped={summary['already_scoped_noop']}, "
        f"ambiguous={summary['skipped_ambiguous']}, "
        f"no_membership={summary['skipped_no_membership']}, "
        f"no_created_by={summary['skipped_no_created_by']}, "
        f"inactive_user={summary['skipped_inactive_user']}, "
        f"existing_values={summary['skipped_existing_values']}, "
        f"errors={summary['errors']}"
    )


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    return str(value)
