import json

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UserMembership

from .rbac_membership_reassignment_table_validate import validate_csv


class Command(BaseCommand):
    help = "Apply approved RBAC membership reassignment CSV rows. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="CSV file to apply.")
        parser.add_argument("--apply", action="store_true", help="Write READY rows. Defaults to dry-run.")
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            report = build_apply_report(options["input"], apply=options["apply"])
            if not options["apply"]:
                transaction.set_rollback(True)
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_apply_report(path, *, apply):
    validation = validate_csv(path)
    rows = [plan_row(row, apply=apply) for row in validation["rows"]]
    return {
        "mode": "apply" if apply else "dry-run",
        "write_enabled": bool(apply),
        "summary": {
            "total": len(rows),
            "planned": sum(1 for row in rows if row["status"] == "PLANNED"),
            "applied": sum(1 for row in rows if row["status"] == "APPLIED"),
            "unchanged": sum(1 for row in rows if row["status"] == "UNCHANGED"),
            "blocked": sum(1 for row in rows if row["status"] == "BLOCKED"),
        },
        "rows": rows,
    }


def plan_row(row, *, apply):
    if row["status"] != "READY":
        return {
            **public_row(row),
            "status": "BLOCKED",
            "previous": None,
            "target": target_state(row),
            "errors": row["errors"],
        }

    membership = (
        UserMembership.objects.select_related("organization", "branch", "department", "role")
        .filter(user__username=row["username"], is_active=True)
        .order_by("-is_primary", "id")
        .first()
    )
    if membership is None:
        return {
            **public_row(row),
            "status": "BLOCKED",
            "previous": None,
            "target": target_state(row),
            "errors": ["active membership not found"],
        }

    previous = membership_state(membership)
    target = target_state(row)
    unchanged = previous == target
    status = "UNCHANGED" if unchanged else ("APPLIED" if apply else "PLANNED")
    if apply and not unchanged:
        membership.organization_id = row["target_organization_id"]
        membership.branch_id = row["target_branch_id"]
        membership.department_id = row["target_department_id"]
        membership.role_id = row["target_role_id"]
        membership.save(update_fields=["organization", "branch", "department", "role", "updated_at"])
    return {
        **public_row(row),
        "status": status,
        "previous": previous,
        "target": target,
        "errors": [],
    }


def public_row(row):
    return {
        "row_number": row["row_number"],
        "username": row["username"],
    }


def membership_state(membership):
    return {
        "organization": label(membership.organization),
        "branch": label(membership.branch),
        "department": label(membership.department),
        "role": getattr(membership.role, "code", None),
    }


def target_state(row):
    return {
        "organization": row["target_organization"],
        "branch": row["target_branch"],
        "department": row["target_department"],
        "role": row["target_role"],
    }


def label(value):
    if value is None:
        return None
    return getattr(value, "name", None) or getattr(value, "code", None) or str(value)


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC membership reassignment apply")
    stdout.write("==================================")
    stdout.write(f"Mode: {report['mode']}")
    stdout.write(
        "Summary: "
        f"total={summary['total']}, planned={summary['planned']}, applied={summary['applied']}, "
        f"unchanged={summary['unchanged']}, blocked={summary['blocked']}"
    )
    stdout.write("")
    stdout.write("rows:")
    for row in report["rows"]:
        errors = "; ".join(row["errors"]) if row["errors"] else "-"
        stdout.write(
            f"  - row={row['row_number']} username={row['username']} status={row['status']} "
            f"previous={row['previous'] or '-'} target={row['target']} errors={errors}"
        )
