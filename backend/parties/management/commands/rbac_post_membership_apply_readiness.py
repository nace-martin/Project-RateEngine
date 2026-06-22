import json
from collections import Counter

from django.core.management.base import BaseCommand

from accounts.models import CustomUser, UserMembership
from parties.models import Branch, Department, Organization


CANONICAL_ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
CANONICAL_BRANCHES = {
    "EFM PNG": ("Port Moresby", "Lae"),
    "EFM Australia": ("Brisbane",),
    "EFM Fiji": ("Suva",),
    "EFM Solomon Islands": ("Honiara",),
}
CANONICAL_DEPARTMENTS = ("Air Freight", "Sea Freight", "Customs", "Transport")


class Command(BaseCommand):
    help = "Read-only RBAC readiness diagnostics after membership reassignment apply."

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
    organizations = {org.name: org for org in Organization.objects.filter(name__in=CANONICAL_ORGANIZATIONS)}
    branches = list(Branch.objects.select_related("organization").filter(organization__name__in=CANONICAL_ORGANIZATIONS))
    departments = list(
        Department.objects.select_related("organization").filter(organization__name__in=CANONICAL_ORGANIZATIONS)
    )
    memberships = list(
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role")
        .filter(is_active=True)
        .order_by("user__username", "id")
    )
    active_users = list(CustomUser.objects.filter(is_active=True).order_by("username", "id"))

    canonical = canonical_report(organizations, branches, departments)
    membership = membership_report(memberships, active_users)
    blockers = blockers_for(canonical, membership)
    return {
        "write_enabled": False,
        "canonical": canonical,
        "memberships": membership,
        "readiness": {
            "status": "READY_FOR_BACKFILL_PLANNING" if not blockers else "NOT_READY_FOR_BACKFILL_PLANNING",
            "blockers": blockers,
        },
    }


def canonical_report(organizations, branches, departments):
    branch_names_by_org = {}
    for branch in branches:
        branch_names_by_org.setdefault(branch.organization.name, set()).add(branch.name)
    department_names_by_org = {}
    for department in departments:
        department_names_by_org.setdefault(department.organization.name, set()).add(department.name)
    missing_branches = {
        org_name: [name for name in branch_names if name not in branch_names_by_org.get(org_name, set())]
        for org_name, branch_names in CANONICAL_BRANCHES.items()
    }
    missing_departments = {
        org_name: [name for name in CANONICAL_DEPARTMENTS if name not in department_names_by_org.get(org_name, set())]
        for org_name in CANONICAL_ORGANIZATIONS
    }
    return {
        "organizations_present": sorted(organizations),
        "organizations_missing": [name for name in CANONICAL_ORGANIZATIONS if name not in organizations],
        "branches_missing": {org: names for org, names in missing_branches.items() if names},
        "departments_missing": {org: names for org, names in missing_departments.items() if names},
    }


def membership_report(memberships, active_users):
    canonical_orgs = set(CANONICAL_ORGANIZATIONS)
    memberships_by_user = {}
    for membership in memberships:
        memberships_by_user.setdefault(membership.user_id, []).append(membership)
    active_user_ids = {user.id for user in active_users}
    no_membership_users = [user_row(user) for user in active_users if user.id not in memberships_by_user]
    multiple_membership_users = [
        user_row(memberships_for_user[0].user)
        for user_id, memberships_for_user in memberships_by_user.items()
        if user_id in active_user_ids and len(memberships_for_user) > 1
    ]
    return {
        "active_users": len(active_users),
        "active_memberships": len(memberships),
        "complete_canonical_memberships": sum(1 for membership in memberships if membership_is_complete_canonical(membership)),
        "missing_organization": sum(1 for membership in memberships if membership.organization_id is None),
        "missing_branch": sum(1 for membership in memberships if membership.branch_id is None),
        "missing_department": sum(1 for membership in memberships if membership.department_id is None),
        "missing_role": sum(1 for membership in memberships if membership.role_id is None),
        "legacy_non_canonical_organization_memberships": sum(
            1 for membership in memberships if membership.organization and membership.organization.name not in canonical_orgs
        ),
        "users_with_no_active_membership": len(no_membership_users),
        "users_with_multiple_active_memberships": len(multiple_membership_users),
        "no_active_membership_examples": no_membership_users[:10],
        "multiple_active_membership_examples": multiple_membership_users[:10],
        "active_memberships_by_status": dict(sorted(Counter(membership_status(membership) for membership in memberships).items())),
    }


def membership_is_complete_canonical(membership):
    return (
        membership.organization
        and membership.organization.name in CANONICAL_ORGANIZATIONS
        and membership.branch_id
        and membership.department_id
        and membership.role_id
    )


def membership_status(membership):
    if not membership.organization_id:
        return "missing_organization"
    if membership.organization.name not in CANONICAL_ORGANIZATIONS:
        return "legacy_organization"
    if not membership.branch_id:
        return "missing_branch"
    if not membership.department_id:
        return "missing_department"
    if not membership.role_id:
        return "missing_role"
    return "complete_canonical"


def blockers_for(canonical, membership):
    blockers = []
    if canonical["organizations_missing"]:
        blockers.append(f"missing canonical organizations: {canonical['organizations_missing']}")
    if canonical["branches_missing"]:
        blockers.append(f"missing canonical branches: {canonical['branches_missing']}")
    if canonical["departments_missing"]:
        blockers.append(f"missing canonical departments: {canonical['departments_missing']}")
    for key in ("legacy_non_canonical_organization_memberships", "missing_organization", "missing_branch", "missing_department", "missing_role", "users_with_no_active_membership", "users_with_multiple_active_memberships"):
        if membership[key]:
            blockers.append(f"{key}: {membership[key]}")
    return blockers


def user_row(user):
    return {
        "user_id": str(user.id),
        "username": safe(user.username),
        "email": safe(user.email),
    }


def write_text(stdout, report):
    readiness = report["readiness"]
    canonical = report["canonical"]
    membership = report["memberships"]
    stdout.write("RBAC post-membership-apply readiness")
    stdout.write("====================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Readiness: {readiness['status']}")
    stdout.write("")
    stdout.write("Canonical master data:")
    stdout.write(f"  organizations_missing={canonical['organizations_missing']}")
    stdout.write(f"  branches_missing={canonical['branches_missing']}")
    stdout.write(f"  departments_missing={canonical['departments_missing']}")
    stdout.write("")
    stdout.write(
        "Memberships: "
        f"active_users={membership['active_users']}, "
        f"active_memberships={membership['active_memberships']}, "
        f"complete_canonical={membership['complete_canonical_memberships']}, "
        f"missing_org={membership['missing_organization']}, "
        f"missing_branch={membership['missing_branch']}, "
        f"missing_department={membership['missing_department']}, "
        f"missing_role={membership['missing_role']}, "
        f"legacy_org_memberships={membership['legacy_non_canonical_organization_memberships']}, "
        f"users_no_membership={membership['users_with_no_active_membership']}, "
        f"users_multiple_memberships={membership['users_with_multiple_active_memberships']}"
    )
    stdout.write(f"  by_status={membership['active_memberships_by_status']}")
    if readiness["blockers"]:
        stdout.write("")
        stdout.write("Blockers:")
        for blocker in readiness["blockers"]:
            stdout.write(f"  - {blocker}")


def safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")
