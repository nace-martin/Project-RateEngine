import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from accounts.models import UserMembership
from parties.models import Branch, Department, Organization


TARGET_ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
PENDING_ORGANIZATIONS = ("EFM Express Air Cargo",)
TARGET_BRANCHES = {
    "EFM PNG": ("Port Moresby", "Lae"),
    "EFM Australia": ("Brisbane",),
    "EFM Fiji": ("Suva",),
    "EFM Solomon Islands": ("Honiara",),
}
TARGET_DEPARTMENTS = ("Air Freight", "Sea Freight", "Customs", "Transport", "Warehousing")
PENDING_DEPARTMENTS = ("EAC",)
LEGACY_ORG_ACTIONS = {
    "Express Freight Management": "RENAME_CANDIDATE",
    "EFM Express Air Cargo": "RETAIN_PENDING_DECISION",
    "Test Org": "EXCLUDE_TEST",
}
BLOCKERS = (
    "EAC placement unresolved",
    "AU second office unresolved",
    "Fiji second office unresolved",
    "Express Freight Management handling unresolved",
    "Test Org dependency check unresolved",
)


class Command(BaseCommand):
    help = "Read-only proposed RBAC master-data alignment report."

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
            help="Include safe row-level master-data and membership details.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum detail rows per section when --show-details is used.",
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
        self.stdout.write("RBAC master data alignment plan")
        self.stdout.write("================================")
        self.stdout.write("Mode: read-only diagnostics")
        self.stdout.write(f"Readiness: {report['readiness']['write_pr']} / {report['readiness']['historical_backfill']}")

        self.stdout.write("")
        self.stdout.write("Organizations:")
        orgs = report["organizations"]
        self.stdout.write(f"  current={orgs['current']}")
        self.stdout.write(f"  target={orgs['target']}")
        self.stdout.write(f"  missing={orgs['missing']}")
        self.stdout.write(f"  legacy_extra={orgs['legacy_extra']}")
        self.stdout.write(f"  proposed_actions={action_counts(orgs['actions'])}")

        self.stdout.write("")
        self.stdout.write("Branches:")
        branches = report["branches"]
        self.stdout.write(f"  current_by_organization={branches['current_by_organization']}")
        self.stdout.write(f"  target_by_organization={branches['target_by_organization']}")
        self.stdout.write(f"  missing={branches['missing']}")
        self.stdout.write(f"  unexpected_organization={branches['unexpected_organization']}")
        self.stdout.write(f"  proposed_actions={action_counts(branches['actions'])}")

        self.stdout.write("")
        self.stdout.write("Departments:")
        departments = report["departments"]
        self.stdout.write(f"  current_by_organization={departments['current_by_organization']}")
        self.stdout.write(f"  target={departments['target']}")
        self.stdout.write(f"  missing={departments['missing']}")
        self.stdout.write(f"  unexpected={departments['unexpected']}")
        self.stdout.write(f"  proposed_actions={action_counts(departments['actions'])}")

        membership = report["memberships"]
        self.stdout.write("")
        self.stdout.write(
            "Memberships: "
            f"active={membership['active_memberships']}, "
            f"missing_organization={membership['missing_organization']}, "
            f"missing_branch={membership['missing_branch']}, "
            f"missing_department={membership['missing_department']}, "
            f"complete={membership['complete_membership']}, "
            f"null_branch_policy_required={membership['null_branch_policy_required']}, "
            f"users_with_multiple_active_memberships={membership['users_with_multiple_active_memberships']}"
        )

        self.stdout.write("")
        self.stdout.write("Blockers:")
        for blocker in report["blockers"]:
            self.stdout.write(f"  - {blocker}")

        for section, rows in report.get("details", {}).items():
            if not rows:
                continue
            self.stdout.write("")
            self.stdout.write(f"{section}:")
            for row in rows:
                self.stdout.write(f"  - {format_detail(row)}")


def build_report(*, show_details=False, limit=50):
    organizations = list(Organization.objects.order_by("name", "id"))
    branches = list(Branch.objects.select_related("organization").order_by("organization__name", "name", "id"))
    departments = list(
        Department.objects.select_related("organization", "branch").order_by("organization__name", "name", "id")
    )
    memberships = list(
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role")
        .filter(is_active=True)
        .order_by("user__username", "organization__name", "id")
    )

    org_report = organization_report(organizations)
    branch_report = branch_report_for(branches)
    department_report = department_report_for(departments)
    membership_report = membership_report_for(memberships)
    blockers = blockers_for(membership_report)

    report = {
        "write_enabled": False,
        "tenant_concept": "EFM Group is a business tenant concept only; no Tenant model is proposed here.",
        "organizations": org_report,
        "branches": branch_report,
        "departments": department_report,
        "memberships": membership_report,
        "blockers": blockers,
        "readiness": readiness_for(org_report, branch_report, membership_report),
        "safety_rules": [
            "read-only only",
            "no writes, saves, updates, deletes, creates, seed changes, selector changes, enforcement, or backfill",
            "no branch inference from customer name, route, lane, quote text, notes, or free text",
        ],
    }
    if show_details:
        report["details"] = {
            "organization_details": org_report["actions"][:limit],
            "branch_details": branch_report["actions"][:limit],
            "department_details": department_report["actions"][:limit],
            "membership_details": [membership_row(membership) for membership in memberships[:limit]],
        }
    return report


def organization_report(organizations):
    current = [ascii_safe(org.name) for org in organizations]
    current_set = set(current)
    target = list(TARGET_ORGANIZATIONS) + list(PENDING_ORGANIZATIONS)
    actions = []
    for name in target:
        if name in current_set:
            actions.append(action("organization", name, "KEEP"))
        else:
            verb = "DEFER" if name in PENDING_ORGANIZATIONS else "CREATE"
            actions.append(action("organization", name, verb))
    for name in current:
        if name not in target:
            actions.append(action("organization", name, LEGACY_ORG_ACTIONS.get(name, "DEFER")))
    return {
        "current": current,
        "target": target,
        "missing": [name for name in TARGET_ORGANIZATIONS if name not in current_set],
        "legacy_extra": [name for name in current if name not in target],
        "actions": actions,
    }


def branch_report_for(branches):
    current_by_org = {}
    for branch in branches:
        current_by_org.setdefault(ascii_safe(branch.organization.name), []).append(ascii_safe(branch.name))
    for names in current_by_org.values():
        names.sort()

    actions = []
    missing = {}
    for org_name, target_branches in TARGET_BRANCHES.items():
        current_names = set(current_by_org.get(org_name, []))
        for branch_name in target_branches:
            if branch_name in current_names:
                actions.append(branch_action(org_name, branch_name, "KEEP"))
            else:
                actions.append(branch_action(org_name, branch_name, "CREATE"))
                missing.setdefault(org_name, []).append(branch_name)
    actions.append(branch_action("EFM Express Air Cargo", "EAC branch pending", "DEFER"))

    expected_branch_names = {name for names in TARGET_BRANCHES.values() for name in names}
    unexpected = [
        branch_row(branch, "MOVE_CANDIDATE")
        for branch in branches
        if branch.name in expected_branch_names and branch.organization.name not in TARGET_BRANCHES
    ]
    actions.extend(unexpected)
    return {
        "current_by_organization": dict(sorted(current_by_org.items())),
        "target_by_organization": TARGET_BRANCHES,
        "missing": missing,
        "unexpected_organization": unexpected,
        "actions": actions,
    }


def department_report_for(departments):
    current_by_org = {}
    for department in departments:
        current_by_org.setdefault(ascii_safe(department.organization.name), []).append(
            {
                "name": ascii_safe(department.name),
                "branch": scope_label(department.branch),
            }
        )

    actions = []
    all_current_names = {department.name for department in departments}
    for org_name in TARGET_ORGANIZATIONS:
        org_department_names = {department.name for department in departments if department.organization.name == org_name}
        for department_name in TARGET_DEPARTMENTS:
            actions.append(
                {
                    "type": "department",
                    "organization": org_name,
                    "name": department_name,
                    "action": "KEEP" if department_name in org_department_names else "CREATE",
                }
            )
    actions.append({"type": "department", "organization": "EAC pending", "name": "EAC", "action": "DEFER"})
    unexpected = sorted(all_current_names - set(TARGET_DEPARTMENTS) - set(PENDING_DEPARTMENTS))
    return {
        "current_by_organization": dict(sorted(current_by_org.items())),
        "target": list(TARGET_DEPARTMENTS) + list(PENDING_DEPARTMENTS),
        "missing": [row for row in actions if row["action"] == "CREATE"],
        "unexpected": unexpected,
        "actions": actions,
    }


def membership_report_for(memberships):
    users = Counter(membership.user_id for membership in memberships)
    return {
        "active_memberships": len(memberships),
        "missing_organization": sum(1 for membership in memberships if membership.organization_id is None),
        "missing_branch": sum(1 for membership in memberships if membership.branch_id is None),
        "missing_department": sum(1 for membership in memberships if membership.department_id is None),
        "complete_membership": sum(
            1 for membership in memberships if membership.organization_id and membership.branch_id and membership.department_id
        ),
        "null_branch_policy_required": sum(1 for membership in memberships if membership.branch_id is None),
        "users_with_multiple_active_memberships": sum(1 for count in users.values() if count > 1),
    }


def blockers_for(membership):
    blockers = list(BLOCKERS)
    if membership["missing_branch"]:
        blockers.append(f"active memberships missing branch: {membership['missing_branch']}")
    if membership["missing_department"]:
        blockers.append(f"active memberships missing department: {membership['missing_department']}")
    return blockers


def readiness_for(organizations, branches, memberships):
    additive_orgs_ok = all(
        row["action"] in {"KEEP", "CREATE", "RENAME_CANDIDATE", "RETAIN_PENDING_DECISION", "EXCLUDE_TEST", "DEFER"}
        for row in organizations["actions"]
    )
    additive_branches_ok = all(row["action"] in {"KEEP", "CREATE", "MOVE_CANDIDATE", "DEFER"} for row in branches["actions"])
    membership_gaps_reported = all(
        key in memberships for key in ("missing_branch", "missing_department", "complete_membership")
    )
    ready_for_write = additive_orgs_ok and additive_branches_ok and membership_gaps_reported
    return {
        "write_pr": "READY_FOR_WRITE_PR" if ready_for_write else "NOT_READY_FOR_WRITE_PR",
        "seed_planning": "READY_FOR_ADDITIVE_SEED_PLANNING" if ready_for_write else "NOT_READY_FOR_ADDITIVE_SEED_PLANNING",
        "historical_backfill": "NOT_READY_FOR_HISTORICAL_BACKFILL",
        "reason": (
            "Required creates are additive and unresolved decisions are marked as pending/defer; "
            "historical backfill remains blocked until master data and memberships are corrected."
        ),
    }


def action(row_type, name, verb):
    return {"type": row_type, "name": ascii_safe(name), "action": verb}


def branch_action(organization, name, verb):
    return {"type": "branch", "organization": ascii_safe(organization), "name": ascii_safe(name), "action": verb}


def branch_row(branch, verb):
    return {
        "type": "branch",
        "organization": ascii_safe(branch.organization.name),
        "name": ascii_safe(branch.name),
        "action": verb,
    }


def membership_row(membership):
    return {
        "id": str(membership.pk),
        "user_id": str(membership.user_id),
        "username": ascii_safe(membership.user.username),
        "email": ascii_safe(membership.user.email),
        "organization": scope_label(membership.organization),
        "branch": scope_label(membership.branch),
        "department": scope_label(membership.department),
        "role": ascii_safe(getattr(membership.role, "code", "")),
    }


def action_counts(rows):
    return dict(sorted(Counter(row["action"] for row in rows).items()))


def scope_label(value):
    if value is None:
        return None
    return ascii_safe(getattr(value, "name", None) or getattr(value, "code", None) or str(value))


def ascii_safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")


def format_detail(row):
    return ", ".join(f"{key}={value if value is not None else '-'}" for key, value in row.items())
