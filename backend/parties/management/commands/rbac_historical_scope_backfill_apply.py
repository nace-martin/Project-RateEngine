import json

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.scope import get_active_memberships
from crm.models import Interaction, Opportunity, Task
from parties.models import Company, Contact

from .rbac_historical_scope_backfill_plan import SCOPE_FIELDS, classify_record


MODEL_SPECS = {
    "Company": {
        "queryset": lambda: Company.objects.select_related(
            "organization", "branch", "department", "account_owner"
        ).order_by("name", "id"),
        "owner_field": "account_owner",
        "parent_fields": (),
    },
    "Contact": {
        "queryset": lambda: Contact.objects.select_related("company", "organization", "branch", "department").order_by(
            "company__name", "last_name", "first_name", "id"
        ),
        "owner_field": None,
        "parent_fields": ("company",),
    },
    "Opportunity": {
        "queryset": lambda: Opportunity.objects.select_related(
            "company", "owner", "organization", "branch", "department"
        ).order_by("created_at", "id"),
        "owner_field": "owner",
        "parent_fields": ("company",),
    },
    "Interaction": {
        "queryset": lambda: Interaction.objects.select_related(
            "company", "opportunity", "author", "organization", "branch", "department"
        ).order_by("created_at", "id"),
        "owner_field": "author",
        "parent_fields": ("opportunity", "company"),
    },
    "Task": {
        "queryset": lambda: Task.objects.select_related(
            "company", "opportunity", "owner", "organization", "branch", "department"
        ).order_by("due_date", "created_at", "id"),
        "owner_field": "owner",
        "parent_fields": ("opportunity", "company"),
    },
}


class Command(BaseCommand):
    help = "Dry-run by default; optionally backfill safe historical CRM/customer scope."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write safe scope backfills. Defaults to dry-run.")
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if apply:
            with transaction.atomic():
                report = build_report(apply=True)
        else:
            report = build_report(apply=False)

        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report(*, apply):
    models = {model_name: inspect_model(model_name, spec) for model_name, spec in MODEL_SPECS.items()}
    if apply:
        apply_planned_actions(models)
    for payload in models.values():
        payload.pop("_actions", None)
    return {
        "mode": "apply" if apply else "dry-run",
        "write_enabled": apply,
        "models": models,
        "summary": combined_summary(models),
    }


def inspect_model(model_name, spec):
    summary = empty_summary()
    samples = []
    actions = []
    for record in spec["queryset"]():
        classification = classify_record(
            record,
            owner_field=spec["owner_field"],
            parent_fields=spec["parent_fields"],
        )
        action = action_for(record, classification)
        actions.append({"record": record, "action": action})
        summary[action["status"]] += 1
        sample = None
        if action["status"] in {"planned", "skipped", "blocked"} and len(samples) < 10:
            sample = {
                "id": str(record.pk),
                "status": action["status"],
                "source": action["source"],
                "reason": action["reason"],
                "fields": action["fields"],
            }
            action["sample"] = sample
            samples.append(sample)

    return {"summary": summary, "samples": samples, "_actions": actions}


def apply_planned_actions(models):
    for payload in models.values():
        summary = payload["summary"]
        for item in payload["_actions"]:
            action = item["action"]
            if action["status"] != "planned":
                continue
            result = apply_action(item["record"], action)
            summary["planned"] -= 1
            summary[result] += 1
            if action.get("sample"):
                action["sample"]["status"] = result
                if result != "applied":
                    action["sample"]["reason"] = action["reason"]


def apply_action(record, action):
    source_object = action["source_object"]
    fields = [
        field
        for field in action["fields"]
        if not getattr(record, f"{field}_id", None) and getattr(source_object, f"{field}_id", None)
    ]
    if not fields:
        action["reason"] = "safe_evidence_no_missing_fields"
        return "blocked"

    for field in fields:
        setattr(record, field, getattr(source_object, field))
    update_fields = [*fields, "updated_at"] if hasattr(record, "updated_at") else fields
    record.save(update_fields=update_fields)
    return "applied"


def action_for(record, classification):
    if classification["status"] == "complete":
        return empty_action("unchanged", "already_complete")
    if classification["status"] != "backfillable":
        return empty_action("skipped", classification["blocker_reason"])

    source_object = classification["parent"] if classification["source"] == "parent_scope" else None
    if classification["source"] == "owner_membership":
        source_object = next(iter(get_active_memberships(classification["owner"])))
    fields = [
        field
        for field in SCOPE_FIELDS
        if not getattr(record, f"{field}_id", None) and getattr(source_object, f"{field}_id", None)
    ]
    if not fields:
        return empty_action("blocked", "safe_evidence_no_missing_fields")
    return {
        "status": "planned",
        "source": classification["source"],
        "source_object": source_object,
        "reason": None,
        "fields": fields,
    }


def empty_action(status, reason):
    return {"status": status, "source": None, "source_object": None, "reason": reason, "fields": []}


def empty_summary():
    return {"planned": 0, "applied": 0, "unchanged": 0, "skipped": 0, "blocked": 0}


def combined_summary(models):
    summary = empty_summary()
    for payload in models.values():
        for key, value in payload["summary"].items():
            summary[key] += value
    return summary


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC historical scope backfill apply")
    stdout.write("====================================")
    stdout.write(f"Mode: {report['mode']}")
    stdout.write(
        "Summary: "
        f"planned={summary['planned']}, applied={summary['applied']}, unchanged={summary['unchanged']}, "
        f"skipped={summary['skipped']}, blocked={summary['blocked']}"
    )
    for model_name, payload in report["models"].items():
        model_summary = payload["summary"]
        stdout.write(
            f"{model_name}: planned={model_summary['planned']}, applied={model_summary['applied']}, "
            f"unchanged={model_summary['unchanged']}, skipped={model_summary['skipped']}, "
            f"blocked={model_summary['blocked']}"
        )
