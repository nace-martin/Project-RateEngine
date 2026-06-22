import json
from collections import Counter

from django.core.management.base import BaseCommand

from accounts.scope import get_active_memberships
from crm.models import Interaction, Opportunity, Task
from parties.models import Company, Contact


SCOPE_FIELDS = ("organization", "branch", "department")
READY = "READY_FOR_BACKFILL_APPLY"
READY_WITH_EXCLUSIONS = "READY_WITH_MANUAL_REVIEW_EXCLUSIONS"
NOT_READY = "NOT_READY_FOR_BACKFILL_APPLY"
BLOCKER_REASONS = {
    "multiple_owner_memberships",
    "owner_no_active_membership",
    "parent_scope_incomplete",
    "no_safe_evidence",
}
UNSAFE_INFERENCE_RULES = [
    "customer name",
    "route",
    "lane",
    "notes",
    "free text",
    "quote description",
    "email text",
    "inferred branch from geography",
    "inferred department from wording",
]


class Command(BaseCommand):
    help = "Read-only historical CRM/customer scope backfill planning diagnostics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    models = {
        "Company": inspect_model(
            Company.objects.select_related("organization", "branch", "department", "account_owner").order_by("name", "id"),
            owner_field="account_owner",
            label_field="name",
        ),
        "Contact": inspect_model(
            Contact.objects.select_related("company", "organization", "branch", "department").order_by(
                "company__name", "last_name", "first_name", "id"
            ),
            parent_fields=("company",),
            label_func=lambda row: f"{row.first_name} {row.last_name}".strip(),
        ),
        "Opportunity": inspect_model(
            Opportunity.objects.select_related("company", "owner", "organization", "branch", "department").order_by(
                "created_at", "id"
            ),
            owner_field="owner",
            parent_fields=("company",),
            label_field="title",
        ),
        "Interaction": inspect_model(
            Interaction.objects.select_related(
                "company", "opportunity", "author", "organization", "branch", "department"
            ).order_by("created_at", "id"),
            owner_field="author",
            parent_fields=("opportunity", "company"),
            label_field="interaction_type",
        ),
        "Task": inspect_model(
            Task.objects.select_related("company", "opportunity", "owner", "organization", "branch", "department").order_by(
                "due_date", "created_at", "id"
            ),
            owner_field="owner",
            parent_fields=("opportunity", "company"),
            label_field="status",
        ),
    }
    summary = combined_summary(models)
    return {
        "write_enabled": False,
        "readiness_status": readiness_status(summary),
        "proposed_apply_strategy": proposed_apply_strategy(summary),
        "summary": summary,
        "models": models,
        "safe_evidence_sources": [
            "existing complete parent scope",
            "existing complete owner/account_owner active membership",
            "existing complete related customer/company scope",
        ],
        "unsafe_inference_rules": UNSAFE_INFERENCE_RULES,
    }


def readiness_status(summary):
    if summary["unclassified_records"]:
        return NOT_READY
    if summary["manual_review_required"]:
        return READY_WITH_EXCLUSIONS
    return READY


def proposed_apply_strategy(summary):
    apply_eligible = (
        summary["records_backfillable_from_owner_membership"]
        + summary["records_backfillable_from_parent_scope"]
    )
    return {
        "apply_eligible_records": apply_eligible,
        "manual_review_excluded_records": summary["manual_review_required"],
        "allowed_evidence_sources": [
            "owner_membership",
            "parent_scope",
            "related_company_scope",
        ],
        "excluded_blocker_reasons": sorted(BLOCKER_REASONS),
        "next_phase": "controlled dry-run-first backfill apply for apply-eligible records only",
    }


def inspect_model(queryset, *, owner_field=None, parent_fields=(), label_field=None, label_func=None):
    summary = empty_summary()
    blocker_counts = Counter()
    sample_blocked_records = []

    for record in queryset:
        classification = classify_record(record, owner_field=owner_field, parent_fields=parent_fields)
        update_summary(summary, record, classification)
        if classification["blocker_reason"]:
            blocker_counts[classification["blocker_reason"]] += 1
            if len(sample_blocked_records) < 10:
                sample_blocked_records.append(sample_record(record, classification, label_field, label_func))

    for reason in sorted(BLOCKER_REASONS):
        blocker_counts.setdefault(reason, 0)
    return {
        "summary": summary,
        "blocker_reasons": dict(sorted(blocker_counts.items())),
        "sample_blocked_records": sample_blocked_records,
    }


def classify_record(record, *, owner_field, parent_fields):
    if complete_scope(record):
        return {"status": "complete", "source": None, "blocker_reason": None, "parent": None, "owner": None}

    parent = first_parent(record, parent_fields)
    if parent and safe_parent_scope(parent):
        return {"status": "backfillable", "source": "parent_scope", "blocker_reason": None, "parent": parent, "owner": None}

    owner = getattr(record, owner_field, None) if owner_field else None
    memberships = list(get_active_memberships(owner)) if owner else []
    if len(memberships) == 1 and complete_scope(memberships[0]):
        return {
            "status": "backfillable",
            "source": "owner_membership",
            "blocker_reason": None,
            "parent": parent,
            "owner": owner,
        }
    if len(memberships) > 1:
        reason = "multiple_owner_memberships"
    elif owner and not memberships:
        reason = "owner_no_active_membership"
    elif parent and not complete_scope(parent):
        reason = "parent_scope_incomplete"
    else:
        reason = "no_safe_evidence"
    return {"status": "blocked", "source": None, "blocker_reason": reason, "parent": parent, "owner": owner}


def first_parent(record, parent_fields):
    for field in parent_fields:
        parent = getattr(record, field, None)
        if parent is not None:
            return parent
    return None


def safe_parent_scope(parent):
    if not complete_scope(parent):
        return False
    parent_owner = getattr(parent, "account_owner", None) or getattr(parent, "owner", None)
    parent_memberships = list(get_active_memberships(parent_owner)) if parent_owner else []
    return not (len(parent_memberships) == 1 and complete_scope(parent_memberships[0]))


def complete_scope(record):
    return all(getattr(record, f"{field}_id", None) for field in SCOPE_FIELDS)


def update_summary(summary, record, classification):
    summary["total_records"] += 1
    for field in SCOPE_FIELDS:
        if not getattr(record, f"{field}_id", None):
            summary[f"records_missing_{field}"] += 1
    if classification["status"] == "complete":
        summary["records_complete"] += 1
    elif classification["source"] == "owner_membership":
        summary["records_backfillable_from_owner_membership"] += 1
    elif classification["source"] == "parent_scope":
        summary["records_backfillable_from_parent_scope"] += 1
    elif classification["blocker_reason"] == "multiple_owner_memberships":
        summary["records_blocked_owner_multiple_active_memberships"] += 1
    elif classification["blocker_reason"] == "owner_no_active_membership":
        summary["records_blocked_owner_no_active_membership"] += 1
    elif classification["blocker_reason"] == "parent_scope_incomplete":
        summary["records_blocked_parent_scope_incomplete"] += 1
    elif classification["blocker_reason"] == "no_safe_evidence":
        summary["records_blocked_no_safe_evidence"] += 1
    else:
        summary["unclassified_records"] += 1


def empty_summary():
    return {
        "total_records": 0,
        "records_missing_organization": 0,
        "records_missing_branch": 0,
        "records_missing_department": 0,
        "records_complete": 0,
        "records_backfillable_from_owner_membership": 0,
        "records_backfillable_from_parent_scope": 0,
        "records_blocked_owner_multiple_active_memberships": 0,
        "records_blocked_owner_no_active_membership": 0,
        "records_blocked_parent_scope_incomplete": 0,
        "records_blocked_no_safe_evidence": 0,
        "unclassified_records": 0,
    }


def combined_summary(models):
    summary = empty_summary()
    for payload in models.values():
        for key, value in payload["summary"].items():
            summary[key] += value
    summary["manual_review_required"] = (
        summary["records_blocked_owner_multiple_active_memberships"]
        + summary["records_blocked_owner_no_active_membership"]
        + summary["records_blocked_parent_scope_incomplete"]
        + summary["records_blocked_no_safe_evidence"]
    )
    return summary


def sample_record(record, classification, label_field, label_func):
    parent = classification["parent"]
    owner = classification["owner"]
    return {
        "id": str(record.pk),
        "name": ascii_safe(label_func(record) if label_func else getattr(record, label_field, "")),
        "blocker_reason": classification["blocker_reason"],
        "owner_evidence": owner_evidence(owner),
        "parent_evidence": parent_evidence(parent),
    }


def owner_evidence(owner):
    if owner is None:
        return None
    memberships = list(get_active_memberships(owner))
    return {
        "username": ascii_safe(owner.username),
        "active_memberships": len(memberships),
        "complete_active_memberships": sum(1 for membership in memberships if complete_scope(membership)),
    }


def parent_evidence(parent):
    if parent is None:
        return None
    return {
        "model": parent.__class__.__name__,
        "id": str(parent.pk),
        "scope_complete": complete_scope(parent),
        "missing_scope": [field for field in SCOPE_FIELDS if not getattr(parent, f"{field}_id", None)],
    }


def write_text(stdout, report):
    stdout.write("RBAC historical scope backfill plan")
    stdout.write("===================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Readiness: {report['readiness_status']}")
    summary = report["summary"]
    stdout.write(
        "Combined totals: "
        f"total={summary['total_records']}, complete={summary['records_complete']}, "
        f"owner_backfillable={summary['records_backfillable_from_owner_membership']}, "
        f"parent_backfillable={summary['records_backfillable_from_parent_scope']}, "
        f"manual_review={summary['manual_review_required']}"
    )
    strategy = report["proposed_apply_strategy"]
    stdout.write(
        "Apply strategy: "
        f"safe apply candidates={strategy['apply_eligible_records']}, "
        f"manual-review exclusions={strategy['manual_review_excluded_records']}"
    )
    stdout.write("Next apply command must exclude manual-review records unless separately approved.")
    for model_name, payload in report["models"].items():
        summary = payload["summary"]
        stdout.write("")
        stdout.write(f"{model_name}:")
        stdout.write(
            f"  total={summary['total_records']}, missing_org={summary['records_missing_organization']}, "
            f"missing_branch={summary['records_missing_branch']}, "
            f"missing_department={summary['records_missing_department']}, complete={summary['records_complete']}"
        )
        stdout.write(
            f"  owner_backfillable={summary['records_backfillable_from_owner_membership']}, "
            f"parent_backfillable={summary['records_backfillable_from_parent_scope']}, "
            f"owner_multiple={summary['records_blocked_owner_multiple_active_memberships']}, "
            f"owner_none={summary['records_blocked_owner_no_active_membership']}, "
            f"parent_incomplete={summary['records_blocked_parent_scope_incomplete']}, "
            f"no_safe_evidence={summary['records_blocked_no_safe_evidence']}"
        )
        for sample in payload["sample_blocked_records"]:
            stdout.write(
                f"  - blocked id={sample['id']} name={sample['name'] or '-'} "
                f"reason={sample['blocker_reason']}"
            )


def ascii_safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")
