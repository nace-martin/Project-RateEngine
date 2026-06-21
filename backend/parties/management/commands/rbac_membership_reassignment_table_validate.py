import csv
import json

from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser, Role
from parties.models import Branch, Department, Organization


REQUIRED_COLUMNS = (
    "username",
    "target_organization",
    "target_branch",
    "target_department",
    "target_role",
    "approved",
    "notes",
)
CANONICAL_ORGANIZATIONS = {"EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands"}
CANONICAL_DEPARTMENTS = {"Air Freight", "Sea Freight", "Customs", "Transport"}
EAC_VALUES = {"eac", "efm express air cargo", "express air cargo"}
TRUE_VALUES = {"true", "yes"}


class Command(BaseCommand):
    help = "Read-only validation for an explicit RBAC membership reassignment CSV table."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="CSV file to validate.")
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )

    def handle(self, *args, **options):
        report = validate_csv(options["input"])
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def validate_csv(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
            if missing_columns:
                raise CommandError(f"Missing required columns: {', '.join(missing_columns)}")
            rows = [validate_row(row_number, row) for row_number, row in enumerate(reader, start=2)]
    except OSError as exc:
        raise CommandError(f"Unable to read input CSV: {exc}") from exc

    seen = {}
    for row in rows:
        username = row["username"]
        if not username:
            continue
        if username in seen:
            row["errors"].append("duplicate username")
            seen[username]["errors"].append("duplicate username")
        else:
            seen[username] = row

    for row in rows:
        row["status"] = "READY" if not row["errors"] else "BLOCKED"

    return {
        "write_enabled": False,
        "summary": {
            "total": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "READY"),
            "blocked": sum(1 for row in rows if row["status"] == "BLOCKED"),
        },
        "rows": rows,
    }


def validate_row(row_number, row):
    values = {column: clean(row.get(column)) for column in REQUIRED_COLUMNS}
    errors = []
    for column in REQUIRED_COLUMNS[:-1]:
        if not values[column]:
            errors.append(f"missing {column}")

    user = CustomUser.objects.filter(username=values["username"]).first()
    if values["username"] and user is None:
        errors.append("user not found")
    elif user and not user.is_active:
        errors.append("user inactive")

    organization = Organization.objects.filter(name=values["target_organization"]).first()
    if contains_eac(values["target_organization"]):
        errors.append("EAC target value is not allowed")
    elif values["target_organization"] and values["target_organization"] not in CANONICAL_ORGANIZATIONS:
        errors.append("target organization is not canonical")
    elif values["target_organization"] and organization is None:
        errors.append("target organization not found")

    branch = None
    if contains_eac(values["target_branch"]):
        errors.append("EAC target value is not allowed")
    elif organization and values["target_branch"]:
        branch = Branch.objects.filter(organization=organization, name=values["target_branch"]).first()
        if branch is None:
            errors.append("target branch not found under target organization")

    if contains_eac(values["target_department"]):
        errors.append("EAC target value is not allowed")
    elif values["target_department"] and values["target_department"] not in CANONICAL_DEPARTMENTS:
        errors.append("target department is not canonical")
    elif organization and values["target_department"]:
        department_exists = Department.objects.filter(
            organization=organization,
            name=values["target_department"],
        ).exists()
        if not department_exists:
            errors.append("target department not found under target organization")

    if values["target_role"] and not Role.objects.filter(code=values["target_role"], is_active=True).exists():
        errors.append("target role not found")

    if values["approved"].lower() not in TRUE_VALUES:
        errors.append("approved must be true or yes")

    return {
        "row_number": row_number,
        **values,
        "target_branch_id": str(branch.pk) if branch else None,
        "status": "BLOCKED",
        "errors": errors,
    }


def clean(value):
    return (value or "").strip()


def contains_eac(value):
    return clean(value).lower() in EAC_VALUES


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC membership reassignment table validation")
    stdout.write("============================================")
    stdout.write("Mode: read-only validation")
    stdout.write(f"Summary: total={summary['total']}, ready={summary['ready']}, blocked={summary['blocked']}")
    stdout.write("")
    stdout.write("rows:")
    for row in report["rows"]:
        errors = "; ".join(row["errors"]) if row["errors"] else "-"
        stdout.write(
            f"  - row={row['row_number']} username={row['username'] or '-'} "
            f"target={row['target_organization'] or '-'}/{row['target_branch'] or '-'}/{row['target_department'] or '-'} "
            f"role={row['target_role'] or '-'} status={row['status']} errors={errors}"
        )
