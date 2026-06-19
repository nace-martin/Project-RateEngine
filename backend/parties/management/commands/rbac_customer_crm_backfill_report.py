import json
from collections import Counter
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from accounts.scope import SCOPE_FIELD_NAMES, get_active_memberships
from crm.models import Interaction, Opportunity, Task
from parties.models import Company, Contact


SOURCE_ALREADY_SCOPED = "already_scoped"
SOURCE_PARENT = "parent_scope"
SOURCE_LINKED_QUOTE = "linked_quote_scope"
SOURCE_SINGLE_MEMBERSHIP = "single_membership"
SOURCE_SHARED_MEMBERSHIPS = "shared_memberships"
SOURCE_UNRESOLVED = "unresolved"

REASON_ALREADY_SCOPED = "already_scoped"
REASON_PARENT_SCOPE = "parent_scope"
REASON_LINKED_QUOTE_SCOPE = "linked_quote_scope"
REASON_SINGLE_MEMBERSHIP = "single_active_membership"
REASON_SHARED_MEMBERSHIPS = "multiple_memberships_shared_values_only"
REASON_MULTIPLE_MEMBERSHIPS = "multiple_memberships_ambiguous"
REASON_NO_SAFE_SOURCE = "no_safe_scope_source"


@dataclass
class Candidate:
    values: dict
    source: str
    reason: str


class Command(BaseCommand):
    help = "Read-only dry-run report for Customer/CRM RBAC scope backfill candidates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )
        parser.add_argument(
            "--show-details",
            action="store_true",
            help="Include safe per-record candidate details.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum detail rows per model when --show-details is used.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be a positive integer.")

        report = build_report(show_details=options["show_details"], limit=options["limit"])
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        self._write_text(report)

    def _write_text(self, report):
        self.stdout.write("Customer/CRM RBAC backfill candidate report")
        self.stdout.write("==========================================")
        self.stdout.write("Mode: read-only dry-run")
        summary = report["summary"]
        self.stdout.write(
            "Combined totals: "
            f"total={summary['total_records']}, "
            f"already_scoped={summary['already_scoped']}, "
            f"missing_scope={summary['missing_any_scope']}, "
            f"safe_candidates={summary['safe_candidates']}, "
            f"unsafe_or_ambiguous={summary['unsafe_or_ambiguous']}"
        )

        for model_name, payload in report["models"].items():
            summary = payload["summary"]
            self.stdout.write("")
            self.stdout.write(f"{model_name}:")
            self.stdout.write(
                f"  total={summary['total_records']}, "
                f"already_scoped={summary['already_scoped']}, "
                f"missing_org={summary['missing_organization']}, "
                f"missing_branch={summary['missing_branch']}, "
                f"missing_department={summary['missing_department']}, "
                f"safe_candidates={summary['safe_candidates']}, "
                f"unsafe_or_ambiguous={summary['unsafe_or_ambiguous']}"
            )
            self.stdout.write(f"  candidate_sources={payload['candidate_sources']}")
            self.stdout.write(f"  ambiguity_reasons={payload['ambiguity_reasons']}")
            for detail in payload.get("details", []):
                candidate = detail["candidate"]
                self.stdout.write(
                    f"  - {detail['model']} {detail['id']} "
                    f"name={detail['label'] or '-'} "
                    f"source={detail['candidate_source']} "
                    f"org={candidate['organization'] or '-'} "
                    f"branch={candidate['branch'] or '-'} "
                    f"department={candidate['department'] or '-'} "
                    f"unresolved={','.join(detail['unresolved_fields']) or '-'} "
                    f"reason={detail['ambiguity_reason']}"
                )


def build_report(*, show_details=False, limit=50):
    models = {
        "company": inspect_records(
            "company",
            Company.objects.select_related("organization", "branch", "department", "account_owner").order_by("name", "id"),
            show_details=show_details,
            limit=limit,
        ),
        "contact": inspect_records(
            "contact",
            Contact.objects.select_related("company", "organization", "branch", "department").order_by("company__name", "last_name", "id"),
            show_details=show_details,
            limit=limit,
        ),
        "opportunity": inspect_records(
            "opportunity",
            Opportunity.objects.select_related(
                "company",
                "owner",
                "organization",
                "branch",
                "department",
            ).prefetch_related("quotes").order_by("created_at", "id"),
            show_details=show_details,
            limit=limit,
        ),
        "interaction": inspect_records(
            "interaction",
            Interaction.objects.select_related(
                "company",
                "opportunity",
                "author",
                "organization",
                "branch",
                "department",
            ).prefetch_related("opportunity__quotes").order_by("created_at", "id"),
            show_details=show_details,
            limit=limit,
        ),
        "task": inspect_records(
            "task",
            Task.objects.select_related(
                "company",
                "opportunity",
                "owner",
                "organization",
                "branch",
                "department",
            ).prefetch_related("opportunity__quotes").order_by("created_at", "id"),
            show_details=show_details,
            limit=limit,
        ),
    }
    return {
        "write_enabled": False,
        "summary": combined_summary(models),
        "models": models,
        "unsafe_inference_rules": [
            "route",
            "lane",
            "origin/destination",
            "customer name",
            "department text",
            "service type",
            "quote lane",
            "free text",
        ],
    }


def inspect_records(model_name, queryset, *, show_details, limit):
    summary = empty_summary()
    source_counts = Counter()
    reason_counts = Counter()
    details = []

    for record in queryset:
        detail = inspect_record(model_name, record)
        update_summary(summary, detail)
        source_counts[detail["candidate_source"]] += 1
        reason_counts[detail["ambiguity_reason"]] += 1
        if show_details and len(details) < limit:
            details.append(detail)

    payload = {
        "summary": summary,
        "candidate_sources": dict(sorted(source_counts.items())),
        "ambiguity_reasons": dict(sorted(reason_counts.items())),
    }
    if show_details:
        payload["details"] = details
    return payload


def inspect_record(model_name, record):
    candidate = candidate_for_record(model_name, record)
    candidate_values = dict(candidate.values)
    unresolved = [field for field in SCOPE_FIELD_NAMES if candidate_values.get(field) is None]
    current_values = {field: getattr(record, field, None) for field in SCOPE_FIELD_NAMES}
    missing_any = any(value is None for value in current_values.values())
    safe = not unresolved
    return {
        "model": model_name,
        "id": str(record.pk),
        "label": safe_label(model_name, record),
        "already_scoped": all(current_values.values()),
        "missing_any_scope": missing_any,
        "missing_fields": [field for field, value in current_values.items() if value is None],
        "safe_candidate": safe,
        "candidate_source": candidate.source,
        "candidate": {field: scope_label(candidate_values.get(field)) for field in SCOPE_FIELD_NAMES},
        "unresolved_fields": unresolved,
        "ambiguity_reason": candidate.reason if unresolved else candidate.reason,
    }


def candidate_for_record(model_name, record):
    values = {field: getattr(record, field, None) for field in SCOPE_FIELD_NAMES}
    if all(values.values()):
        return Candidate(values, SOURCE_ALREADY_SCOPED, REASON_ALREADY_SCOPED)

    parent_candidate = candidate_from_parents(model_name, record, values)
    if parent_candidate:
        return parent_candidate

    quote_candidate = candidate_from_quote(record, values)
    if quote_candidate:
        return quote_candidate

    user = owner_user(model_name, record)
    membership_candidate = candidate_from_memberships(user, values)
    if membership_candidate:
        return membership_candidate

    return Candidate(values, SOURCE_UNRESOLVED, REASON_NO_SAFE_SOURCE)


def candidate_from_parents(model_name, record, values):
    parents = []
    if model_name == "contact":
        parents = [record.company]
    elif model_name == "opportunity":
        parents = [record.company]
    elif model_name in {"interaction", "task"}:
        parents = [getattr(record, "opportunity", None), getattr(record, "company", None)]

    merged = merge_from_sources(values, parents)
    if merged != values:
        return Candidate(merged, SOURCE_PARENT, REASON_PARENT_SCOPE)
    return None


def candidate_from_quote(record, values):
    quotes = []
    if isinstance(record, Opportunity):
        quotes = list(record.quotes.all())
    elif isinstance(record, (Interaction, Task)) and getattr(record, "opportunity_id", None):
        quotes = list(record.opportunity.quotes.all())

    scoped_quotes = [quote for quote in quotes if any(getattr(quote, f"{field}_id", None) for field in SCOPE_FIELD_NAMES)]
    merged = merge_from_sources(values, scoped_quotes)
    if merged != values:
        return Candidate(merged, SOURCE_LINKED_QUOTE, REASON_LINKED_QUOTE_SCOPE)
    return None


def candidate_from_memberships(user, values):
    memberships = list(get_active_memberships(user))
    if len(memberships) == 1:
        merged = merge_from_sources(values, memberships)
        if merged != values:
            return Candidate(merged, SOURCE_SINGLE_MEMBERSHIP, REASON_SINGLE_MEMBERSHIP)
        return None
    if len(memberships) > 1:
        merged = dict(values)
        for field in SCOPE_FIELD_NAMES:
            if merged[field] is not None:
                continue
            ids = {getattr(membership, f"{field}_id", None) for membership in memberships}
            if len(ids) == 1 and next(iter(ids)) is not None:
                merged[field] = getattr(memberships[0], field)
        if merged != values:
            return Candidate(merged, SOURCE_SHARED_MEMBERSHIPS, REASON_SHARED_MEMBERSHIPS)
        return Candidate(values, SOURCE_UNRESOLVED, REASON_MULTIPLE_MEMBERSHIPS)
    return None


def merge_from_sources(values, sources):
    merged = dict(values)
    for field in SCOPE_FIELD_NAMES:
        if merged[field] is not None:
            continue
        matches = {
            getattr(source, f"{field}_id", None)
            for source in sources
            if source is not None and getattr(source, f"{field}_id", None)
        }
        if len(matches) == 1:
            for source in sources:
                if source is not None and getattr(source, f"{field}_id", None) in matches:
                    merged[field] = getattr(source, field)
                    break
    return merged


def owner_user(model_name, record):
    if model_name == "company":
        return record.account_owner
    if model_name == "opportunity":
        return record.owner
    if model_name == "interaction":
        return record.author
    if model_name == "task":
        return record.owner
    return None


def empty_summary():
    return {
        "total_records": 0,
        "already_scoped": 0,
        "missing_any_scope": 0,
        "missing_organization": 0,
        "missing_branch": 0,
        "missing_department": 0,
        "safe_candidates": 0,
        "unsafe_or_ambiguous": 0,
    }


def update_summary(summary, detail):
    summary["total_records"] += 1
    if detail["already_scoped"]:
        summary["already_scoped"] += 1
    if detail["missing_any_scope"]:
        summary["missing_any_scope"] += 1
    for field in detail["missing_fields"]:
        summary[f"missing_{field}"] += 1
    if detail["safe_candidate"]:
        summary["safe_candidates"] += 1
    else:
        summary["unsafe_or_ambiguous"] += 1


def combined_summary(models):
    summary = empty_summary()
    for payload in models.values():
        for key, value in payload["summary"].items():
            summary[key] += value
    return summary


def safe_label(model_name, record):
    if model_name == "company":
        return ascii_safe(record.name)
    if model_name == "contact":
        return ascii_safe(f"{record.first_name} {record.last_name}".strip())
    if model_name == "opportunity":
        return ascii_safe(record.title)
    if model_name == "interaction":
        return record.interaction_type
    if model_name == "task":
        return record.status
    return ""


def scope_label(value):
    if value is None:
        return None
    name = getattr(value, "name", None) or getattr(value, "code", None) or str(value)
    return ascii_safe(f"{value.pk}:{name}")


def ascii_safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")
