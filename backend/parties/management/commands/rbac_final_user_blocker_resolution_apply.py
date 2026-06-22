import json

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser, Role, UserMembership
from parties.models import Branch, Department, Organization
from quotes.spot_models import SpotPricingEnvelopeDB

from .rbac_final_user_blocker_resolution_plan import SYSADMIN_TARGET, candidate_admin_users, membership_state
from .rbac_obsolete_user_cleanup_plan import dependency_counts, empty_counts


class Command(BaseCommand):
    help = "Dry-run by default; optionally apply final RBAC user blocker resolution."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write final blocker fixes. Defaults to dry-run.")
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        with transaction.atomic():
            report = build_apply_report(apply=apply)
            if not apply or report["summary"]["blocked"]:
                transaction.set_rollback(True)
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_apply_report(*, apply):
    context = resolve_context()
    actions = [testuser_action(context, apply=False), sysadmin_action(context, apply=False)]
    blocked_count = sum(1 for row in actions if row["status"] == "BLOCKED")
    if apply and blocked_count == 0:
        actions = [testuser_action(context, apply=True), sysadmin_action(context, apply=True)]
    return {
        "mode": "apply" if apply else "dry-run",
        "write_enabled": bool(apply) and blocked_count == 0,
        "resolver_errors": context["errors"],
        "summary": {
            "total": len(actions),
            "planned": sum(1 for row in actions if row["status"] == "PLANNED"),
            "applied": sum(1 for row in actions if row["status"] == "APPLIED"),
            "unchanged": sum(1 for row in actions if row["status"] == "UNCHANGED"),
            "blocked": sum(1 for row in actions if row["status"] == "BLOCKED"),
        },
        "actions": actions,
    }


def resolve_context():
    errors = []
    target_admin = resolve_target_admin(errors)
    target_scope = resolve_sysadmin_scope(errors)
    sysadmin_count = CustomUser.objects.filter(username="sysadmin").count()
    if sysadmin_count != 1:
        errors.append(f"sysadmin user resolved {sysadmin_count} rows")
    elif UserMembership.objects.filter(user__username="sysadmin", is_active=True).count() > 1:
        errors.append("multiple active sysadmin memberships")
    return {"target_admin": target_admin, "target_scope": target_scope, "errors": errors}


def resolve_target_admin(errors):
    candidates = candidate_admin_users()
    preferred = [
        row for row in candidates if row["username"] == "nason.martin" or row["email"].lower().startswith("nason.martin")
    ]
    selected = preferred[0] if len(preferred) == 1 else (candidates[0] if len(candidates) == 1 else None)
    if selected is None:
        errors.append("target admin user could not be resolved uniquely")
        return None
    return CustomUser.objects.get(id=selected["user_id"])


def resolve_sysadmin_scope(errors):
    target = SYSADMIN_TARGET
    org = one(Organization.objects.filter(name=target["organization"]), "target organization", errors)
    branch = one(Branch.objects.filter(organization=org, name=target["branch"]), "target branch", errors) if org else None
    department = (
        one(Department.objects.filter(organization=org, name=target["department"]), "target department", errors)
        if org
        else None
    )
    role = one(Role.objects.filter(organization__isnull=True, code=target["role"]), "target role", errors)
    if not all([org, branch, department, role]):
        return None
    return {"organization": org, "branch": branch, "department": department, "role": role}


def one(queryset, name, errors):
    count = queryset.count()
    if count != 1:
        errors.append(f"{name} resolved {count} rows")
        return None
    return queryset.get()


def testuser_action(context, *, apply):
    user = CustomUser.objects.filter(username="testuser").first()
    before = dependency_counts(user) if user else empty_counts()
    row = base_action("testuser", "RESOLVE_TESTUSER_SPOT_CREATED_BY", before)
    if context["errors"]:
        return blocked(row, context["errors"])
    if user is None:
        return blocked(row, ["testuser not found"])
    if not user.is_active and sum(before.values()) == 0:
        row.update({"status": "UNCHANGED", "after_dependency_counts": before, "details": ["testuser already inactive"]})
        return row

    spot_count = SpotPricingEnvelopeDB.objects.filter(created_by=user).count()
    was_active = user.is_active
    if apply and spot_count:
        SpotPricingEnvelopeDB.objects.filter(created_by=user).update(created_by=context["target_admin"])
    after = dependency_counts(user) if apply else simulated_testuser_counts(before)
    details = [f"spot_created_by_reassigned={spot_count}", f"target_user={context['target_admin'].username}"]
    if sum(after.values()) == 0 and not UserMembership.objects.filter(user=user, is_active=True).exists():
        if apply and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        details.append("testuser_deactivated=True")
        status = "APPLIED" if apply and (spot_count or was_active) else ("PLANNED" if not apply else "UNCHANGED")
    else:
        details.append("testuser_deactivated=False")
        status = "BLOCKED"
    row.update({"status": status, "after_dependency_counts": after, "details": details})
    return row


def simulated_testuser_counts(counts):
    after = dict(counts)
    after["spot_envelope_created_by"] = 0
    return after


def sysadmin_action(context, *, apply):
    user = CustomUser.objects.filter(username="sysadmin").first()
    before = dependency_counts(user) if user else empty_counts()
    row = base_action("sysadmin", "RESOLVE_SYSADMIN_MEMBERSHIP", before)
    if context["errors"]:
        return blocked(row, context["errors"])
    if user is None:
        return blocked(row, ["sysadmin not found"])

    active = list(
        UserMembership.objects.select_related("organization", "branch", "department", "role")
        .filter(user=user, is_active=True)
        .order_by("id")
    )
    if len(active) > 1:
        return blocked(row, ["multiple active sysadmin memberships"])

    target = context["target_scope"]
    if len(active) == 1 and membership_matches(active[0], target):
        row.update(
            {
                "status": "UNCHANGED",
                "after_dependency_counts": before,
                "details": ["sysadmin canonical membership already active"],
            }
        )
        return row

    if apply:
        if active:
            active[0].is_active = False
            active[0].save(update_fields=["is_active", "updated_at"])
        UserMembership.objects.create(user=user, is_primary=True, is_active=True, **target)
    row.update(
        {
            "status": "APPLIED" if apply else "PLANNED",
            "after_dependency_counts": before,
            "details": [
                f"previous={membership_state(active[0]) if active else None}",
                "target=EFM PNG / Port Moresby / Air Freight / admin",
            ],
        }
    )
    return row


def membership_matches(membership, target):
    return (
        membership.organization_id == target["organization"].id
        and membership.branch_id == target["branch"].id
        and membership.department_id == target["department"].id
        and membership.role_id == target["role"].id
    )


def base_action(username, action, before):
    return {
        "username": username,
        "action": action,
        "status": "PLANNED",
        "before_dependency_counts": before,
        "after_dependency_counts": before,
        "details": [],
    }


def blocked(row, errors):
    row.update({"status": "BLOCKED", "details": list(errors)})
    return row


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC final user blocker resolution apply")
    stdout.write("========================================")
    stdout.write(f"Mode: {report['mode']}")
    stdout.write(
        "Summary: "
        f"total={summary['total']}, planned={summary['planned']}, applied={summary['applied']}, "
        f"unchanged={summary['unchanged']}, blocked={summary['blocked']}"
    )
    for row in report["actions"]:
        stdout.write(
            f"  - username={row['username']} status={row['status']} action={row['action']} "
            f"details={'; '.join(row['details']) or '-'}"
        )
