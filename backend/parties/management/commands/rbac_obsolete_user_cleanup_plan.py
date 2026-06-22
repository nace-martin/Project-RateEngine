import json

from django.core.management.base import BaseCommand

from accounts.models import CustomUser, UserMembership
from crm.models import Interaction, Opportunity, Task
from parties.models import Company
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB


OBSOLETE_USERNAMES = ("finance", "nas", "system_user", "testuser", "unassigned_user")


class Command(BaseCommand):
    help = "Read-only plan for obsolete/test/duplicate RBAC user cleanup."

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
    rows = [inspect_user(username) for username in OBSOLETE_USERNAMES]
    summary = {
        "total": len(rows),
        "deactivate_user": sum(1 for row in rows if row["recommended_action"] == "DEACTIVATE_USER"),
        "deactivate_membership": sum(
            1 for row in rows if row["recommended_action"] == "DEACTIVATE_MEMBERSHIP"
        ),
        "review_dependencies": sum(1 for row in rows if row["recommended_action"] == "REVIEW_DEPENDENCIES"),
        "not_found": sum(1 for row in rows if row["recommended_action"] == "NOT_FOUND"),
    }
    return {
        "write_enabled": False,
        "safety": [
            "read-only only",
            "no user deletion or deactivation",
            "no membership modification",
            "no CRM/customer backfill",
            "no RBAC enforcement",
        ],
        "summary": summary,
        "users": rows,
    }


def inspect_user(username):
    user = CustomUser.objects.filter(username=username).first()
    if user is None:
        return {
            "username": username,
            "is_active": None,
            "current_organization": "",
            "branch": "",
            "department": "",
            "role": "",
            "has_active_membership": False,
            "dependency_counts": empty_counts(),
            "recommended_action": "NOT_FOUND",
            "blocker_reason": "user not found",
        }

    membership = (
        UserMembership.objects.select_related("organization", "branch", "department", "role")
        .filter(user=user, is_active=True)
        .order_by("-is_primary", "id")
        .first()
    )
    counts = dependency_counts(user)
    total_dependencies = sum(counts.values())
    if total_dependencies:
        action = "REVIEW_DEPENDENCIES"
        reason = f"{total_dependencies} related ownership/dependency record(s) require review"
    elif membership:
        action = "DEACTIVATE_MEMBERSHIP"
        reason = "active membership exists; deactivate membership before retiring user"
    else:
        action = "DEACTIVATE_USER"
        reason = "no active membership or counted ownership dependencies"

    return {
        "username": username,
        "is_active": user.is_active,
        "current_organization": label(membership.organization if membership else user.organization),
        "branch": label(membership.branch if membership else None),
        "department": label(membership.department) if membership else safe(user.department),
        "role": safe(getattr(membership.role, "code", "")) if membership else safe(user.role),
        "has_active_membership": bool(membership),
        "dependency_counts": counts,
        "recommended_action": action,
        "blocker_reason": reason,
    }


def dependency_counts(user):
    return {
        "customer_account_owner": Company.objects.filter(account_owner=user).count(),
        "crm_opportunity_owner": Opportunity.objects.filter(owner=user).count(),
        "crm_opportunity_won_by": Opportunity.objects.filter(won_by=user).count(),
        "crm_interaction_author": Interaction.objects.filter(author=user).count(),
        "crm_task_owner": Task.objects.filter(owner=user).count(),
        "crm_task_completed_by": Task.objects.filter(completed_by=user).count(),
        "quote_created_by": Quote.objects.filter(created_by=user).count(),
        "quote_owner": Quote.objects.filter(owner=user).count(),
        "quote_finalized_by": Quote.objects.filter(finalized_by=user).count(),
        "quote_sent_by": Quote.objects.filter(sent_by=user).count(),
        "spot_envelope_created_by": SpotPricingEnvelopeDB.objects.filter(created_by=user).count(),
        "spot_envelope_owner": SpotPricingEnvelopeDB.objects.filter(owner=user).count(),
    }


def empty_counts():
    return {
        "customer_account_owner": 0,
        "crm_opportunity_owner": 0,
        "crm_opportunity_won_by": 0,
        "crm_interaction_author": 0,
        "crm_task_owner": 0,
        "crm_task_completed_by": 0,
        "quote_created_by": 0,
        "quote_owner": 0,
        "quote_finalized_by": 0,
        "quote_sent_by": 0,
        "spot_envelope_created_by": 0,
        "spot_envelope_owner": 0,
    }


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC obsolete user cleanup plan")
    stdout.write("===============================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(
        "Summary: "
        f"total={summary['total']}, "
        f"deactivate_user={summary['deactivate_user']}, "
        f"deactivate_membership={summary['deactivate_membership']}, "
        f"review_dependencies={summary['review_dependencies']}, "
        f"not_found={summary['not_found']}"
    )
    stdout.write("")
    stdout.write("users:")
    for row in report["users"]:
        deps = sum(row["dependency_counts"].values())
        stdout.write(
            f"  - username={row['username']} is_active={row['is_active']} "
            f"org={row['current_organization'] or '-'} branch={row['branch'] or '-'} "
            f"department={row['department'] or '-'} role={row['role'] or '-'} "
            f"active_membership={row['has_active_membership']} dependencies={deps} "
            f"action={row['recommended_action']} blocker={row['blocker_reason']}"
        )


def label(value):
    if value is None:
        return ""
    return safe(getattr(value, "name", None) or getattr(value, "code", None) or str(value))


def safe(value):
    if value is None:
        return ""
    return str(value).encode("ascii", "replace").decode("ascii")
