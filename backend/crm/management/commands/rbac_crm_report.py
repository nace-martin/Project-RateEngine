import json

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db.models import Count

from crm.models import Interaction, Opportunity, Task


class Command(BaseCommand):
    help = "Read-only CRM RBAC discovery report."

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
            help="Include safe per-record identifiers.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum detail rows per model when --show-details is used.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be a positive integer.")

        report = build_report(show_details=options["show_details"], limit=limit)

        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self._write_text(report)

    def _write_text(self, report):
        self.stdout.write("CRM RBAC discovery report")
        self.stdout.write("=========================")
        self.stdout.write("Mode: read-only")
        self.stdout.write(
            "Combined totals: "
            f"total={report['summary']['total_records']}, "
            f"with_owner={report['summary']['with_owner_or_author']}, "
            f"missing_owner={report['summary']['missing_owner_or_author']}, "
            f"linked_company={report['summary']['linked_to_company']}, "
            f"linked_customer_company={report['summary']['linked_to_customer_company']}, "
            f"linked_quote={report['summary']['linked_to_quote']}, "
            f"scope_fields={report['summary']['with_org_branch_department_scope']}, "
            f"likely_global={report['summary']['likely_globally_accessible_today']}"
        )
        self.stdout.write("")
        self.stdout.write("Current access: authenticated users can read CRM list/detail endpoints globally.")
        self.stdout.write("Future scoping fields available: owner/author, company, opportunity, quote via opportunity.")
        self.stdout.write("Missing durable scope fields: organization, branch, department.")

        for model_name, payload in report["models"].items():
            summary = payload["summary"]
            self.stdout.write("")
            self.stdout.write(f"{model_name}:")
            self.stdout.write(
                f"  total={summary['total_records']}, "
                f"with_owner={summary['with_owner_or_author']}, "
                f"missing_owner={summary['missing_owner_or_author']}, "
                f"linked_company={summary['linked_to_company']}, "
                f"linked_customer_company={summary['linked_to_customer_company']}, "
                f"linked_quote={summary['linked_to_quote']}, "
                f"scope_fields={summary['with_org_branch_department_scope']}, "
                f"likely_global={summary['likely_globally_accessible_today']}"
            )
            self.stdout.write(f"  ownership_fields={', '.join(payload['ownership_fields']) or '-'}")
            self.stdout.write(f"  future_scope_fields={', '.join(payload['future_scope_fields']) or '-'}")
            if "details" in payload:
                for detail in payload["details"]:
                    self.stdout.write(
                        f"  - {detail['model']} {detail['id']}: "
                        f"status={detail.get('status') or detail.get('type') or '-'}, "
                        f"user={detail.get('user') or '-'}, "
                        f"company={detail.get('company') or '-'}, "
                        f"quote={detail.get('quote') or '-'}, "
                        f"created_at={detail.get('created_at') or '-'}"
                    )


def build_report(*, show_details=False, limit=25):
    models = {
        "opportunity": inspect_opportunities(show_details=show_details, limit=limit),
        "interaction": inspect_interactions(show_details=show_details, limit=limit),
        "task": inspect_tasks(show_details=show_details, limit=limit),
    }
    return {
        "write_enabled": False,
        "summary": combined_summary(models),
        "models": models,
        "access_risk": {
            "list_detail_reads": "authenticated_global",
            "direct_id_access": "global_queryset",
            "enforcement_changed": False,
        },
    }


def inspect_opportunities(*, show_details, limit):
    queryset = Opportunity.objects.select_related("company", "owner").annotate(quote_count=Count("quotes"))
    summary = base_summary(queryset.count())
    summary.update(
        with_owner_or_author=queryset.filter(owner__isnull=False).count(),
        missing_owner_or_author=queryset.filter(owner__isnull=True).count(),
        linked_to_company=queryset.filter(company__isnull=False).count(),
        linked_to_customer_company=queryset.filter(company__is_customer=True).count(),
        linked_to_quote=queryset.filter(quote_count__gt=0).count(),
    )
    finalize_global(summary)
    payload = model_payload(
        summary,
        ownership_fields=["owner", "won_by"],
        future_scope_fields=["owner", "company", "quotes"],
    )
    if show_details:
        payload["details"] = [
            {
                "id": str(row.id),
                "model": "opportunity",
                "status": row.status,
                "user": getattr(row.owner, "username", None),
                "company": company_label(row.company),
                "quote": quote_label(row.quotes.first()),
                "created_at": datetime_or_none(row.created_at),
            }
            for row in queryset.order_by("created_at", "id")[:limit]
        ]
    return payload


def inspect_interactions(*, show_details, limit):
    queryset = Interaction.objects.select_related("company", "opportunity", "author").annotate(
        quote_count=Count("opportunity__quotes")
    )
    summary = base_summary(queryset.count())
    summary.update(
        with_owner_or_author=queryset.filter(author__isnull=False).count(),
        missing_owner_or_author=queryset.filter(author__isnull=True).count(),
        linked_to_company=queryset.filter(company__isnull=False).count(),
        linked_to_customer_company=queryset.filter(company__is_customer=True).count(),
        linked_to_quote=queryset.filter(quote_count__gt=0).count(),
    )
    finalize_global(summary)
    payload = model_payload(
        summary,
        ownership_fields=["author"],
        future_scope_fields=["author", "company", "opportunity", "opportunity.quotes"],
    )
    if show_details:
        payload["details"] = [
            {
                "id": str(row.id),
                "model": "interaction",
                "type": row.interaction_type,
                "user": getattr(row.author, "username", None),
                "company": company_label(row.company),
                "quote": quote_label(row.opportunity.quotes.first()) if row.opportunity_id else None,
                "created_at": datetime_or_none(row.created_at),
            }
            for row in queryset.order_by("created_at", "id")[:limit]
        ]
    return payload


def inspect_tasks(*, show_details, limit):
    queryset = Task.objects.select_related("company", "opportunity", "owner").annotate(
        quote_count=Count("opportunity__quotes")
    )
    summary = base_summary(queryset.count())
    summary.update(
        with_owner_or_author=queryset.filter(owner__isnull=False).count(),
        missing_owner_or_author=queryset.filter(owner__isnull=True).count(),
        linked_to_company=queryset.filter(company__isnull=False).count(),
        linked_to_customer_company=queryset.filter(company__is_customer=True).count(),
        linked_to_quote=queryset.filter(quote_count__gt=0).count(),
    )
    finalize_global(summary)
    payload = model_payload(
        summary,
        ownership_fields=["owner", "completed_by"],
        future_scope_fields=["owner", "company", "opportunity", "opportunity.quotes"],
    )
    if show_details:
        payload["details"] = [
            {
                "id": str(row.id),
                "model": "task",
                "status": row.status,
                "user": getattr(row.owner, "username", None),
                "company": company_label(row.company),
                "quote": quote_label(row.opportunity.quotes.first()) if row.opportunity_id else None,
                "created_at": datetime_or_none(row.created_at),
            }
            for row in queryset.order_by("created_at", "id")[:limit]
        ]
    return payload


def base_summary(total):
    return {
        "total_records": total,
        "with_owner_or_author": 0,
        "missing_owner_or_author": 0,
        "linked_to_company": 0,
        "linked_to_customer_company": 0,
        "linked_to_quote": 0,
        "with_org_branch_department_scope": 0,
        "likely_globally_accessible_today": 0,
    }


def finalize_global(summary):
    summary["likely_globally_accessible_today"] = summary["total_records"]


def model_payload(summary, *, ownership_fields, future_scope_fields):
    return {
        "summary": summary,
        "ownership_fields": ownership_fields,
        "future_scope_fields": future_scope_fields,
        "missing_durable_scope_fields": ["organization", "branch", "department"],
    }


def combined_summary(models):
    summary = base_summary(0)
    for payload in models.values():
        for key, value in payload["summary"].items():
            summary[key] += value
    return summary


def company_label(company):
    if company is None:
        return None
    return f"{company.id}:{company.name}"


def quote_label(quote):
    if quote is None:
        return None
    return getattr(quote, "quote_number", None) or str(quote.id)


def datetime_or_none(value):
    if value is None:
        return None
    return value.isoformat()
