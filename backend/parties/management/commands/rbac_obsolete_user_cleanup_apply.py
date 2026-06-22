import json

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser, UserMembership

from .rbac_obsolete_user_cleanup_plan import dependency_counts, empty_counts, label, safe


APPROVED_USERNAMES = ("finance", "nas", "system_user", "unassigned_user")
EXCLUDED_USERNAMES = ("testuser",)


class Command(BaseCommand):
    help = "Dry-run by default; optionally deactivate approved obsolete users or memberships."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write approved cleanup actions. Defaults to dry-run.")
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
            if not apply:
                transaction.set_rollback(True)
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_apply_report(*, apply):
    rows = [inspect_user(username, apply=apply) for username in APPROVED_USERNAMES]
    skipped = [skipped_test_user(username) for username in EXCLUDED_USERNAMES]
    blockers = [row for row in rows if row["status"] == "BLOCKED_DEPENDENCIES"]
    actions = [row for row in rows if row["status"] in ("PLANNED", "APPLIED", "UNCHANGED")]
    return {
        "mode": "apply" if apply else "dry-run",
        "write_enabled": bool(apply),
        "approved_targets": list(APPROVED_USERNAMES),
        "excluded_targets": list(EXCLUDED_USERNAMES),
        "summary": {
            "total": len(rows) + len(skipped),
            "planned": sum(1 for row in rows if row["status"] == "PLANNED"),
            "applied": sum(1 for row in rows if row["status"] == "APPLIED"),
            "unchanged": sum(1 for row in rows if row["status"] == "UNCHANGED"),
            "skipped": len(skipped) + sum(1 for row in rows if row["status"] == "NOT_FOUND"),
            "dependency_blockers": len(blockers),
        },
        "planned_actions": [row for row in actions if row["status"] == "PLANNED"],
        "applied_actions": [row for row in actions if row["status"] == "APPLIED"],
        "skipped_users": skipped + [row for row in rows if row["status"] == "NOT_FOUND"],
        "dependency_blockers": blockers,
        "users": rows + skipped,
    }


def inspect_user(username, *, apply):
    user = CustomUser.objects.filter(username=username).first()
    if user is None:
        return base_row(username, "NOT_FOUND", "user not found", None, None, empty_counts())

    membership = active_membership(user)
    counts = dependency_counts(user)
    if sum(counts.values()):
        return base_row(
            username,
            "BLOCKED_DEPENDENCIES",
            "dependency counts must be reviewed before cleanup",
            user,
            membership,
            counts,
        )

    if membership is not None:
        if apply:
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
        return base_row(
            username,
            "APPLIED" if apply else "PLANNED",
            "deactivate active membership only",
            user,
            membership,
            counts,
            action="DEACTIVATE_MEMBERSHIP",
        )

    if not user.is_active:
        return base_row(
            username,
            "UNCHANGED",
            "user already inactive",
            user,
            None,
            counts,
            action="DEACTIVATE_USER",
        )

    if apply:
        user.is_active = False
        user.save(update_fields=["is_active"])
    return base_row(
        username,
        "APPLIED" if apply else "PLANNED",
        "deactivate user; no active membership or counted dependencies",
        user,
        None,
        counts,
        action="DEACTIVATE_USER",
    )


def active_membership(user):
    return (
        UserMembership.objects.select_related("organization", "branch", "department", "role")
        .filter(user=user, is_active=True)
        .order_by("-is_primary", "id")
        .first()
    )


def base_row(username, status, reason, user, membership, counts, *, action="SKIP"):
    return {
        "username": username,
        "status": status,
        "action": action,
        "reason": reason,
        "is_active": None if user is None else user.is_active,
        "current_organization": label(membership.organization if membership else getattr(user, "organization", None)),
        "branch": label(membership.branch) if membership else "",
        "department": label(membership.department) if membership else safe(getattr(user, "department", "")),
        "role": safe(getattr(membership.role, "code", "")) if membership else safe(getattr(user, "role", "")),
        "has_active_membership": bool(membership),
        "dependency_counts": counts,
    }


def skipped_test_user(username):
    return {
        "username": username,
        "status": "SKIPPED_DEPENDENCY_REVIEW_REQUIRED",
        "action": "SKIP",
        "reason": "testuser explicitly excluded from Phase 8T apply",
        "is_active": None,
        "current_organization": "",
        "branch": "",
        "department": "",
        "role": "",
        "has_active_membership": False,
        "dependency_counts": empty_counts(),
    }


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC obsolete user cleanup apply")
    stdout.write("================================")
    stdout.write(f"Mode: {report['mode']}")
    stdout.write(
        "Summary: "
        f"total={summary['total']}, planned={summary['planned']}, applied={summary['applied']}, "
        f"unchanged={summary['unchanged']}, skipped={summary['skipped']}, "
        f"dependency_blockers={summary['dependency_blockers']}"
    )
    write_rows(stdout, "planned actions", report["planned_actions"])
    write_rows(stdout, "applied actions", report["applied_actions"])
    write_rows(stdout, "skipped users", report["skipped_users"])
    write_rows(stdout, "dependency blockers", report["dependency_blockers"])


def write_rows(stdout, title, rows):
    stdout.write("")
    stdout.write(f"{title}:")
    if not rows:
        stdout.write("  - none")
        return
    for row in rows:
        deps = sum(row["dependency_counts"].values())
        stdout.write(
            f"  - username={row['username']} status={row['status']} action={row['action']} "
            f"active_membership={row['has_active_membership']} dependencies={deps} reason={row['reason']}"
        )
