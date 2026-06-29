import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from accounts.models import UserMembership
from parties.models import Branch, Department, OperatingEntity, Organization


CANONICAL_ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
CANONICAL_TOP_ORGANIZATION = "Express Freight Management"
CANONICAL_BRANCHES = {
    "EFM PNG": ("Port Moresby", "Lae"),
    "EFM Australia": ("Brisbane",),
    "EFM Fiji": ("Suva",),
    "EFM Solomon Islands": ("Honiara",),
}
CANONICAL_DEPARTMENTS = ("Air Freight", "Sea Freight", "Customs", "Transport")
LEGACY_EAC_NAMES = {"EAC", "EFM Express Air Cargo", "Express Air Cargo"}


class Command(BaseCommand):
    help = "Read-only plan for moving active memberships from legacy orgs to canonical RBAC master data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum text rows to print. JSON always includes all rows.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be a positive integer.")
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report, limit=options["limit"])


def build_report():
    memberships = (
        UserMembership.objects.select_related("user", "organization", "operating_entity", "branch", "department", "role")
        .filter(is_active=True)
        .order_by("user__username", "organization__name", "id")
    )
    rows = [plan_membership(membership) for membership in memberships]
    return {
        "write_enabled": False,
        "safety": [
            "read-only only",
            "no CRM/customer backfill",
            "no RBAC enforcement",
            "no free-text, route, lane, quote, note, task, or customer-name inference",
            "EAC is legacy wording only; Air Freight is the canonical department when explicitly safe",
        ],
        "summary": dict(sorted(Counter(row["status"] for row in rows).items())),
        "memberships": rows,
    }


def plan_membership(membership):
    current_org = membership.organization
    current_branch = membership.branch
    current_department = membership.department

    suggested_org = suggest_organization(current_org)
    suggested_operating_entity = suggest_operating_entity(membership, suggested_org)
    suggested_department = suggest_department(current_department)
    suggested_branch, branch_reason = suggest_branch(suggested_org, suggested_operating_entity, current_branch)
    status, reason = status_for(
        current_org=current_org,
        current_branch=current_branch,
        current_department=current_department,
        suggested_org=suggested_org,
        suggested_branch=suggested_branch,
        suggested_department=suggested_department,
        branch_reason=branch_reason,
    )
    return {
        "user_id": str(membership.user_id),
        "username": safe(membership.user.username),
        "email": safe(membership.user.email),
        "current_organization": label(current_org),
        "current_branch": label(current_branch),
        "current_department": label(current_department),
        "current_role": safe(getattr(membership.role, "code", "")),
        "suggested_organization": suggested_org,
        "suggested_operating_entity": suggested_operating_entity,
        "suggested_branch": suggested_branch,
        "suggested_department": suggested_department,
        "status": status,
        "reason": reason,
    }


def suggest_organization(organization):
    if organization and organization.name in (CANONICAL_TOP_ORGANIZATION, *CANONICAL_ORGANIZATIONS):
        return CANONICAL_TOP_ORGANIZATION
    return None


def suggest_operating_entity(membership, suggested_org):
    if membership.operating_entity_id:
        return membership.operating_entity.name
    if membership.branch_id and membership.branch.operating_entity_id:
        return membership.branch.operating_entity.name
    if membership.organization and membership.organization.name in CANONICAL_ORGANIZATIONS:
        entity = OperatingEntity.objects.filter(name=membership.organization.name).first()
        if entity:
            return entity.name
        return membership.organization.name
    return suggested_org if suggested_org in CANONICAL_ORGANIZATIONS else None


def suggest_branch(suggested_org, suggested_operating_entity, current_branch):
    if not suggested_org:
        return None, "organization is not canonical"
    entity_name = current_branch.operating_entity.name if current_branch and current_branch.operating_entity_id else None
    canonical = CANONICAL_BRANCHES.get(entity_name or suggested_operating_entity) or ()
    if current_branch and current_branch.name in canonical:
        return current_branch.name, "current branch is canonical"
    if len(canonical) == 1:
        return canonical[0], "single canonical branch"
    return None, "multiple canonical branches require manual choice"


def suggest_department(department):
    if department is None:
        return None
    if department.name in CANONICAL_DEPARTMENTS:
        return department.name
    if department.name in LEGACY_EAC_NAMES or department.code in LEGACY_EAC_NAMES:
        return "Air Freight"
    return None


def status_for(*, current_org, current_branch, current_department, suggested_org, suggested_branch, suggested_department, branch_reason):
    org_canonical = bool(current_org and current_org.name == CANONICAL_TOP_ORGANIZATION)
    branch_canonical = bool(suggested_branch and current_branch and current_branch.name == suggested_branch)
    department_canonical = bool(
        suggested_department and current_department and current_department.name == suggested_department
    )
    if org_canonical and branch_canonical and department_canonical:
        return "ALREADY_CANONICAL", "membership already has canonical organization, branch, and department"
    if not suggested_org:
        if suggested_department:
            return "NEEDS_MANUAL_DECISION", "legacy organization requires human target organization and branch decision"
        return "NEEDS_MANUAL_DECISION", "legacy organization is not safely mappable to a canonical organization"
    if not suggested_branch:
        return "BLOCKED", branch_reason
    if not suggested_department:
        return "NEEDS_MANUAL_DECISION", "department is missing or not safely canonical"
    return "READY", "canonical organization plus deterministic branch/department suggestion"


def write_text(stdout, report, *, limit):
    stdout.write("RBAC membership reassignment plan")
    stdout.write("=================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Summary: {report['summary']}")
    stdout.write("")
    stdout.write("memberships:")
    for row in report["memberships"][:limit]:
        stdout.write(
            "  - "
            f"user_id={row['user_id']} username={row['username']} "
            f"current_org={row['current_organization'] or '-'} "
            f"current_branch={row['current_branch'] or '-'} "
            f"current_department={row['current_department'] or '-'} "
            f"suggested_org={row['suggested_organization'] or '-'} "
            f"suggested_operating_entity={row['suggested_operating_entity'] or '-'} "
            f"suggested_branch={row['suggested_branch'] or '-'} "
            f"suggested_department={row['suggested_department'] or '-'} "
            f"status={row['status']} reason={row['reason']}"
        )
    remaining = len(report["memberships"]) - limit
    if remaining > 0:
        stdout.write(f"... {remaining} more memberships omitted; use --limit or --format json")


def label(value):
    if value is None:
        return None
    return safe(getattr(value, "name", None) or getattr(value, "code", None) or str(value))


def safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")
