import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from accounts.scope import SCOPE_FIELD_NAMES, get_active_memberships
from crm.models import Interaction, Opportunity, Task
from parties.models import Branch, Company, Contact, Department, Organization
from quotes.models import Quote


COVERAGE_KEYS = (
    "organization_only",
    "organization_department",
    "organization_branch",
    "organization_branch_department",
    "no_scope",
    "other_partial",
)


class Command(BaseCommand):
    help = "Read-only CRM/customer RBAC scope completeness diagnostics."

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
            help="Include safe per-record scope details.",
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
        readiness = report["readiness"]
        self.stdout.write("RBAC scope completeness report")
        self.stdout.write("==============================")
        self.stdout.write("Mode: read-only diagnostics")
        self.stdout.write(
            "Readiness: "
            f"organization={readiness['organization_readiness_percent']}%, "
            f"branch={readiness['branch_readiness_percent']}%, "
            f"department={readiness['department_readiness_percent']}%, "
            f"overall={readiness['overall']}"
        )
        self.stdout.write(f"Reason: {readiness['reason']}")

        organizations = report["organizations"]
        self.stdout.write("")
        self.stdout.write(
            "Organizations: "
            f"total={organizations['total_organizations']}, "
            f"active={organizations['active_organizations']}"
        )
        for org in organizations["by_organization"]:
            self.stdout.write(
                f"  - {org['id']} {org['name']}: "
                f"branches={org['branches']}, active_branches={org['active_branches']}, "
                f"departments={org['departments']}, active_departments={org['active_departments']}"
            )

        self.stdout.write("")
        self.stdout.write("Branch coverage:")
        for model_name, payload in report["branch_coverage"].items():
            self.stdout.write(
                f"  {model_name}: total={payload['total']}, "
                f"org_only={payload['organization_only']}, "
                f"org_dept={payload['organization_department']}, "
                f"org_branch={payload['organization_branch']}, "
                f"org_branch_dept={payload['organization_branch_department']}, "
                f"no_scope={payload['no_scope']}, "
                f"other_partial={payload['other_partial']}"
            )

        membership = report["membership_coverage"]
        self.stdout.write("")
        self.stdout.write(
            "Membership coverage: "
            f"referenced_users={membership['referenced_users']}, "
            f"one_active={membership['users_with_one_active_membership']}, "
            f"multiple_active={membership['users_with_multiple_memberships']}, "
            f"no_active={membership['users_with_no_memberships']}"
        )
        self.stdout.write(
            "  populated: "
            f"organization={membership['organization_populated']}, "
            f"branch={membership['branch_populated']}, "
            f"department={membership['department_populated']}"
        )

        self.stdout.write("")
        self.stdout.write("Quote coverage:")
        quote = report["quote_coverage"]
        self.stdout.write(
            f"  linked_quotes={quote['linked_quotes']}, "
            f"org_only={quote['organization_only']}, "
            f"org_dept={quote['organization_department']}, "
            f"org_branch={quote['organization_branch']}, "
            f"org_branch_dept={quote['organization_branch_department']}, "
            f"no_scope={quote['no_scope']}, "
            f"other_partial={quote['other_partial']}"
        )

        self.stdout.write("")
        self.stdout.write("Branch discovery analysis:")
        for source, payload in report["branch_discovery"].items():
            self.stdout.write(
                f"  {source}: candidates={payload['candidate_count']}, "
                f"complete={payload['complete_count']}, "
                f"partial={payload['partial_count']}, "
                f"impossible={payload['impossible_count']}"
            )

        for model_name, details in report.get("details", {}).items():
            if not details:
                continue
            self.stdout.write("")
            self.stdout.write(f"{model_name} details:")
            for row in details:
                self.stdout.write(
                    f"  - {row['model']} {row['id']} label={row['label'] or '-'} "
                    f"scope={row['scope_state']} "
                    f"derived_org={row['derivable']['organization']} "
                    f"derived_branch={row['derivable']['branch']} "
                    f"derived_department={row['derivable']['department']} "
                    f"sources={','.join(row['sources']) or '-'}"
                )


def build_report(*, show_details=False, limit=50):
    model_specs = {
        "company": Company.objects.select_related("organization", "branch", "department", "account_owner").order_by("name", "id"),
        "contact": Contact.objects.select_related("company", "organization", "branch", "department").order_by("company__name", "last_name", "id"),
        "opportunity": Opportunity.objects.select_related(
            "company",
            "owner",
            "won_by",
            "organization",
            "branch",
            "department",
        ).prefetch_related("quotes").order_by("created_at", "id"),
        "interaction": Interaction.objects.select_related(
            "company",
            "opportunity",
            "author",
            "organization",
            "branch",
            "department",
        ).prefetch_related("opportunity__quotes").order_by("created_at", "id"),
        "task": Task.objects.select_related(
            "company",
            "opportunity",
            "owner",
            "completed_by",
            "organization",
            "branch",
            "department",
        ).prefetch_related("opportunity__quotes").order_by("created_at", "id"),
    }

    branch_coverage = {}
    details = {}
    readiness_counts = {field: {"ready": 0, "total": 0} for field in SCOPE_FIELD_NAMES}
    discovery = {
        "quote_scope": empty_discovery(),
        "memberships": empty_discovery(),
        "company_scope": empty_discovery(),
        "customer_scope": empty_discovery(),
    }

    for model_name, queryset in model_specs.items():
        branch_coverage[model_name] = empty_coverage()
        details[model_name] = []
        for record in queryset:
            scope_state = scope_coverage_key(record)
            branch_coverage[model_name]["total"] += 1
            branch_coverage[model_name][scope_state] += 1

            source_values = source_scope_values(model_name, record)
            for source, values in source_values.items():
                update_discovery(discovery[source], values)

            derivable = derivable_fields(record, source_values)
            for field in SCOPE_FIELD_NAMES:
                readiness_counts[field]["total"] += 1
                if derivable[field]:
                    readiness_counts[field]["ready"] += 1

            if show_details and len(details[model_name]) < limit:
                details[model_name].append(
                    {
                        "model": model_name,
                        "id": str(record.pk),
                        "label": safe_label(model_name, record),
                        "scope_state": scope_state,
                        "current_scope": current_scope(record),
                        "derivable": derivable,
                        "sources": [source for source, values in source_values.items() if any(values.values())],
                    }
                )

    report = {
        "write_enabled": False,
        "organizations": organization_summary(),
        "branch_coverage": branch_coverage,
        "membership_coverage": membership_coverage(),
        "quote_coverage": quote_coverage(),
        "branch_discovery": discovery,
        "readiness": readiness_summary(readiness_counts),
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
    if show_details:
        report["details"] = details
    return report


def organization_summary():
    rows = []
    for organization in Organization.objects.order_by("name", "id"):
        branches = list(organization.branches.all())
        departments = list(organization.departments.all())
        rows.append(
            {
                "id": str(organization.pk),
                "name": ascii_safe(organization.name),
                "is_active": organization.is_active,
                "branches": len(branches),
                "active_branches": sum(1 for branch in branches if branch.is_active),
                "departments": len(departments),
                "active_departments": sum(1 for department in departments if department.is_active),
            }
        )
    return {
        "total_organizations": Organization.objects.count(),
        "active_organizations": Organization.objects.filter(is_active=True).count(),
        "by_organization": rows,
    }


def membership_coverage():
    users = referenced_users()
    summary = {
        "referenced_users": len(users),
        "users_with_one_active_membership": 0,
        "users_with_multiple_memberships": 0,
        "users_with_no_memberships": 0,
        "organization_populated": 0,
        "branch_populated": 0,
        "department_populated": 0,
        "referenced_by_field": dict(sorted(referenced_user_field_counts().items())),
    }
    for user in users:
        memberships = list(get_active_memberships(user))
        if len(memberships) == 1:
            summary["users_with_one_active_membership"] += 1
        elif len(memberships) > 1:
            summary["users_with_multiple_memberships"] += 1
        else:
            summary["users_with_no_memberships"] += 1
        if any(membership.organization_id for membership in memberships):
            summary["organization_populated"] += 1
        if any(membership.branch_id for membership in memberships):
            summary["branch_populated"] += 1
        if any(membership.department_id for membership in memberships):
            summary["department_populated"] += 1
    return summary


def quote_coverage():
    quote_ids = linked_quote_ids()
    coverage = empty_coverage()
    coverage["linked_quotes"] = 0
    for quote in Quote.objects.filter(pk__in=quote_ids).select_related("organization", "branch", "department").order_by("id"):
        coverage["linked_quotes"] += 1
        coverage[scope_coverage_key(quote)] += 1
    return coverage


def source_scope_values(model_name, record):
    return {
        "quote_scope": quote_scope_values(model_name, record),
        "memberships": membership_scope_values(model_name, record),
        "company_scope": company_scope_values(model_name, record),
        "customer_scope": customer_scope_values(model_name, record),
    }


def quote_scope_values(model_name, record):
    if model_name not in {"opportunity", "interaction", "task"}:
        return empty_scope_bools()
    quotes = linked_quotes_for_record(record)
    return agreed_scope_bools(quotes)


def membership_scope_values(model_name, record):
    users = owner_users(model_name, record)
    memberships = []
    for user in users:
        memberships.extend(list(get_active_memberships(user)))
    return agreed_scope_bools(memberships)


def company_scope_values(model_name, record):
    company = getattr(record, "company", None)
    if model_name == "company":
        return empty_scope_bools()
    return scope_bools(company)


def customer_scope_values(model_name, record):
    if model_name not in {"opportunity", "interaction", "task"}:
        return empty_scope_bools()
    customers = [quote.customer for quote in linked_quotes_for_record(record) if getattr(quote, "customer_id", None)]
    return agreed_scope_bools(customers)


def derivable_fields(record, source_values):
    current = {field: bool(getattr(record, f"{field}_id", None)) for field in SCOPE_FIELD_NAMES}
    derivable = dict(current)
    for field in SCOPE_FIELD_NAMES:
        if derivable[field]:
            continue
        derivable[field] = any(values[field] for values in source_values.values())
    return derivable


def linked_quotes_for_record(record):
    if isinstance(record, Opportunity):
        return list(record.quotes.all())
    opportunity = getattr(record, "opportunity", None)
    if opportunity is None:
        return []
    return list(opportunity.quotes.all())


def linked_quote_ids():
    opportunity_ids = set(Opportunity.objects.values_list("id", flat=True))
    interaction_opportunity_ids = set(
        Interaction.objects.exclude(opportunity_id__isnull=True).values_list("opportunity_id", flat=True)
    )
    return set(
        Quote.objects.filter(opportunity_id__in=opportunity_ids.union(interaction_opportunity_ids)).values_list("id", flat=True)
    )


def owner_users(model_name, record):
    fields = {
        "company": ("account_owner",),
        "opportunity": ("owner", "won_by"),
        "interaction": ("author",),
        "task": ("owner", "completed_by"),
    }.get(model_name, ())
    return [getattr(record, field, None) for field in fields if getattr(record, f"{field}_id", None)]


def referenced_users():
    users = []
    for model, fields in user_reference_fields().items():
        for field in fields:
            users.extend(
                model.objects.exclude(**{f"{field}_id__isnull": True})
                .select_related(field)
                .values_list(field, flat=True)
            )
    from accounts.models import CustomUser

    return list(CustomUser.objects.filter(pk__in=set(users)).order_by("username", "id"))


def referenced_user_field_counts():
    counts = Counter()
    for model, fields in user_reference_fields().items():
        model_name = model._meta.model_name
        for field in fields:
            count = model.objects.exclude(**{f"{field}_id__isnull": True}).values(field).distinct().count()
            counts[f"{model_name}.{field}"] = count
    return counts


def user_reference_fields():
    return {
        Company: ("account_owner",),
        Opportunity: ("owner", "won_by"),
        Interaction: ("author",),
        Task: ("owner", "completed_by"),
    }


def agreed_scope_bools(records):
    records = [record for record in records if record is not None]
    result = {}
    for field in SCOPE_FIELD_NAMES:
        values = {getattr(record, f"{field}_id", None) for record in records if getattr(record, f"{field}_id", None)}
        result[field] = len(values) == 1
    return result


def scope_bools(record):
    if record is None:
        return empty_scope_bools()
    return {field: bool(getattr(record, f"{field}_id", None)) for field in SCOPE_FIELD_NAMES}


def current_scope(record):
    return {
        field: scope_label(getattr(record, field, None))
        for field in SCOPE_FIELD_NAMES
    }


def scope_coverage_key(record):
    org = bool(getattr(record, "organization_id", None))
    branch = bool(getattr(record, "branch_id", None))
    department = bool(getattr(record, "department_id", None))
    if org and branch and department:
        return "organization_branch_department"
    if org and branch and not department:
        return "organization_branch"
    if org and department and not branch:
        return "organization_department"
    if org and not branch and not department:
        return "organization_only"
    if not org and not branch and not department:
        return "no_scope"
    return "other_partial"


def readiness_summary(counts):
    values = {}
    ready_for_backfill = True
    missing = []
    for field, payload in counts.items():
        percent = percent_ready(payload["ready"], payload["total"])
        values[f"{field}_readiness_percent"] = percent
        values[f"{field}_ready_records"] = payload["ready"]
        values[f"{field}_total_records"] = payload["total"]
        if percent < 100:
            ready_for_backfill = False
            missing.append(field)
    values["overall"] = "READY FOR BACKFILL" if ready_for_backfill else "NOT READY FOR BACKFILL"
    if ready_for_backfill:
        values["reason"] = "All customer/CRM records have derivable organization, branch, and department scope."
    else:
        values["reason"] = f"Not all records have safely derivable {', '.join(missing)} scope."
    return values


def percent_ready(ready, total):
    if total == 0:
        return 100.0
    return round((ready / total) * 100, 2)


def empty_coverage():
    coverage = {"total": 0}
    coverage.update({key: 0 for key in COVERAGE_KEYS})
    return coverage


def empty_discovery():
    return {
        "candidate_count": 0,
        "complete_count": 0,
        "partial_count": 0,
        "impossible_count": 0,
    }


def empty_scope_bools():
    return {field: False for field in SCOPE_FIELD_NAMES}


def update_discovery(summary, values):
    summary["candidate_count"] += 1
    populated = sum(1 for value in values.values() if value)
    if populated == len(SCOPE_FIELD_NAMES):
        summary["complete_count"] += 1
    elif populated:
        summary["partial_count"] += 1
    else:
        summary["impossible_count"] += 1


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
