import json

from django.core.management.base import BaseCommand

from accounts.models import CustomUser, UserMembership
from quotes.spot_models import SpotPricingEnvelopeDB

from .rbac_obsolete_user_cleanup_plan import dependency_counts, empty_counts, label, safe
from .rbac_post_membership_apply_readiness import CANONICAL_TOP_ORGANIZATIONS, user_row


SYSADMIN_TARGET = {
    "organization": "Express Freight Management",
    "operating_entity": "EFM PNG",
    "branch": "Port Moresby",
    "department": "Air Freight",
    "role": "admin",
}


class Command(BaseCommand):
    help = "Read-only resolution plan for final RBAC user blockers before backfill planning."

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
    active_users = list(CustomUser.objects.filter(is_active=True).order_by("username", "id"))
    active_memberships = list(
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role")
        .filter(is_active=True)
        .order_by("user__username", "id")
    )
    memberships_by_user = {}
    for membership in active_memberships:
        memberships_by_user.setdefault(membership.user_id, []).append(membership)

    no_membership = [user_plan(user) for user in active_users if user.id not in memberships_by_user]
    legacy = [membership_plan(membership) for membership in active_memberships if is_legacy(membership)]
    missing_scope = [
        membership_plan(membership)
        for membership in active_memberships
        if membership.branch_id is None or membership.department_id is None
    ]

    return {
        "write_enabled": False,
        "safety": [
            "read-only only",
            "no user deactivation",
            "no membership modification",
            "no SPOT reassignment",
            "no CRM/customer backfill",
        ],
        "summary": {
            "active_users_with_no_membership": len(no_membership),
            "legacy_non_canonical_active_memberships": len(legacy),
            "missing_branch_or_department_memberships": len(missing_scope),
        },
        "active_users_with_no_membership": no_membership,
        "legacy_non_canonical_active_memberships": legacy,
        "missing_branch_or_department_memberships": missing_scope,
    }


def user_plan(user):
    counts = dependency_counts(user)
    row = {
        **user_row(user),
        "dependency_counts": counts,
        "recommended_action": "REVIEW_DEPENDENCIES" if sum(counts.values()) else "READY_FOR_DEACTIVATION_REVIEW",
    }
    if user.username == "testuser":
        row.update(testuser_details(user))
    return row


def testuser_details(user):
    envelopes = SpotPricingEnvelopeDB.objects.filter(created_by=user)
    owner_count = envelopes.exclude(owner__isnull=True).count()
    return {
        "spot_envelope_created_by_count": envelopes.count(),
        "spot_envelope_owner_count": owner_count,
        "spot_envelope_missing_owner_count": envelopes.filter(owner__isnull=True).count(),
        "candidate_reassignment_users": candidate_admin_users(),
        "recommended_action": "REVIEW_SPOT_CREATED_BY_REASSIGNMENT",
    }


def candidate_admin_users():
    rows = []
    for user in CustomUser.objects.filter(is_active=True, role=CustomUser.ROLE_ADMIN).order_by("username", "id"):
        memberships = list(
            UserMembership.objects.select_related("organization", "operating_entity", "branch", "department", "role").filter(
                user=user,
                is_active=True,
                role__code=CustomUser.ROLE_ADMIN,
                organization__name__in=CANONICAL_TOP_ORGANIZATIONS,
                branch__isnull=False,
                department__isnull=False,
            )
        )
        if len(memberships) == 1:
            rows.append({**user_row(user), "membership": membership_state(memberships[0])})
    return rows


def membership_plan(membership):
    action = "READY_FOR_MEMBERSHIP_REASSIGNMENT" if membership.user.username == "sysadmin" else "REVIEW_MEMBERSHIP_SCOPE"
    row = {
        **user_row(membership.user),
        "user_exists": True,
        "current_membership": membership_state(membership),
        "dependency_counts": dependency_counts(membership.user),
        "recommended_action": action,
    }
    if membership.user.username == "sysadmin":
        row["candidate_canonical_membership"] = SYSADMIN_TARGET
    return row


def membership_state(membership):
    return {
        "organization": label(membership.organization),
        "operating_entity": label(membership.operating_entity),
        "branch": label(membership.branch),
        "department": label(membership.department),
        "role": safe(getattr(membership.role, "code", "")),
    }


def is_legacy(membership):
    return bool(membership.organization and membership.organization.name not in CANONICAL_TOP_ORGANIZATIONS)


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC final user blocker resolution plan")
    stdout.write("=======================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(
        "Summary: "
        f"users_no_membership={summary['active_users_with_no_membership']}, "
        f"legacy_memberships={summary['legacy_non_canonical_active_memberships']}, "
        f"missing_scope_memberships={summary['missing_branch_or_department_memberships']}"
    )
    write_rows(stdout, "active users with no membership", report["active_users_with_no_membership"])
    write_rows(stdout, "legacy/non-canonical active memberships", report["legacy_non_canonical_active_memberships"])
    write_rows(stdout, "missing branch/department memberships", report["missing_branch_or_department_memberships"])


def write_rows(stdout, title, rows):
    stdout.write("")
    stdout.write(f"{title}:")
    if not rows:
        stdout.write("  - none")
        return
    for row in rows:
        deps = sum(row.get("dependency_counts", empty_counts()).values())
        extra = ""
        if row["username"] == "testuser":
            extra = (
                f" spot_created_by={row['spot_envelope_created_by_count']}"
                f" spot_owner={row['spot_envelope_owner_count']}"
                f" candidates={len(row['candidate_reassignment_users'])}"
            )
        stdout.write(
            f"  - username={row['username']} dependencies={deps} "
            f"action={row['recommended_action']}{extra}"
        )
