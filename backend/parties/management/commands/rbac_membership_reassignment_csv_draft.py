import csv

from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser, UserMembership


FIELDNAMES = (
    "username",
    "current_organization",
    "current_operating_entity",
    "current_branch",
    "current_department",
    "current_role",
    "target_organization",
    "target_operating_entity",
    "target_branch",
    "target_department",
    "target_role",
    "approved",
    "notes",
)
CANONICAL_ORGANIZATIONS = {"Express Freight Management"}


class Command(BaseCommand):
    help = "Read-only CSV draft for approved RBAC membership reassignment preparation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional CSV output path. Defaults to stdout.",
        )

    def handle(self, *args, **options):
        rows = build_rows()
        output = options.get("output")
        if output:
            try:
                with open(output, "w", encoding="utf-8", newline="") as handle:
                    write_csv(handle, rows)
            except OSError as exc:
                raise CommandError(f"Unable to write output CSV: {exc}") from exc
            self.stdout.write(f"Wrote {len(rows)} draft rows to {output}")
            return
        write_csv(self.stdout, rows)


def build_rows():
    active_users = CustomUser.objects.filter(is_active=True).order_by("username", "id")
    memberships = (
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role")
        .filter(is_active=True, user__is_active=True)
        .order_by("user__username", "id")
    )
    memberships_by_user = {}
    for membership in memberships:
        memberships_by_user.setdefault(membership.user_id, []).append(membership)

    rows = []
    for user in active_users:
        user_memberships = memberships_by_user.get(user.id, [])
        if not user_memberships:
            rows.append(row_for_user_without_membership(user))
            continue
        for membership in user_memberships:
            if include_membership(membership):
                rows.append(row_for_membership(membership))
    return rows


def include_membership(membership):
    return not membership_is_complete_canonical(membership)


def membership_is_complete_canonical(membership):
    return (
        membership.organization
        and membership.organization.name in CANONICAL_ORGANIZATIONS
        and membership.operating_entity_id
        and membership.branch_id
        and membership.department_id
        and membership.role_id
    )


def row_for_membership(membership):
    target = target_fields(membership)
    return {
        "username": safe(membership.user.username),
        "current_organization": label(membership.organization),
        "current_operating_entity": label(membership.operating_entity),
        "current_branch": label(membership.branch),
        "current_department": label(membership.department),
        "current_role": safe(getattr(membership.role, "code", "")),
        **target,
        "approved": "",
        "notes": notes_for(membership),
    }


def row_for_user_without_membership(user):
    return {
        "username": safe(user.username),
        "current_organization": label(user.organization),
        "current_branch": "",
        "current_department": safe(user.department),
        "current_role": safe(user.role),
        "target_organization": "",
        "target_operating_entity": "",
        "target_branch": "",
        "target_department": "",
        "target_role": "",
        "approved": "",
        "notes": "no active membership",
    }


def target_fields(membership):
    if membership_is_complete_canonical(membership):
        return {
            "target_organization": label(membership.organization),
            "target_operating_entity": label(membership.operating_entity),
            "target_branch": label(membership.branch),
            "target_department": label(membership.department),
            "target_role": safe(getattr(membership.role, "code", "")),
        }
    return {
        "target_organization": "",
        "target_operating_entity": suggested_operating_entity(membership),
        "target_branch": "",
        "target_department": "",
        "target_role": "",
    }


def notes_for(membership):
    notes = []
    if not membership.organization_id:
        notes.append("missing organization")
    elif membership.organization.name not in CANONICAL_ORGANIZATIONS:
        notes.append("legacy/non-canonical membership")
    if membership.branch_id is None:
        notes.append("missing branch")
    if membership.operating_entity_id is None:
        notes.append("missing operating_entity")
    if membership.department_id is None:
        notes.append("missing department")
    if membership.role_id is None:
        notes.append("missing role")
    return "; ".join(notes)


def suggested_operating_entity(membership):
    if membership.branch_id and membership.branch.operating_entity_id:
        return label(membership.branch.operating_entity)
    return ""


def write_csv(handle, rows):
    writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def label(value):
    if value is None:
        return ""
    return safe(getattr(value, "name", None) or getattr(value, "code", None) or str(value))


def safe(value):
    if value is None:
        return ""
    return str(value).encode("ascii", "replace").decode("ascii")
