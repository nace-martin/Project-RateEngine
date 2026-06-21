from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UserMembership
from parties.models import Branch, Department, Organization


ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
BRANCHES = {
    "EFM PNG": (("POM", "Port Moresby"), ("LAE", "Lae")),
    "EFM Australia": (("BNE", "Brisbane"),),
    "EFM Fiji": (("SUV", "Suva"),),
    "EFM Solomon Islands": (("HIR", "Honiara"),),
}
DEPARTMENTS = (("AIR", "Air Freight"), ("SEA", "Sea Freight"), ("CUS", "Customs"), ("TRN", "Transport"))


class Command(BaseCommand):
    help = "Additively align RBAC master data and deterministic active memberships."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write additive changes. Defaults to dry-run.")

    def handle(self, *args, **options):
        apply = options["apply"]
        with transaction.atomic():
            report = align(apply=apply)
            if not apply:
                transaction.set_rollback(True)
        write_report(self.stdout, report)


def align(*, apply):
    report = {
        "mode": "apply" if apply else "dry-run",
        "organizations": [],
        "branches": [],
        "departments": [],
        "memberships": [],
        "summary": {"created": 0, "existing": 0, "updated": 0, "skipped": 0, "blocked": 0},
    }
    organizations = align_organizations(report, apply=apply)
    branches = align_branches(report, organizations, apply=apply)
    align_departments(report, organizations, apply=apply)
    align_memberships(report, branches, apply=apply)
    return report


def align_organizations(report, *, apply):
    organizations = {}
    for name in ORGANIZATIONS:
        organization = Organization.objects.filter(name=name).first()
        if organization:
            record(report, "organizations", "existing", name)
        else:
            record(report, "organizations", "created", name)
            if apply:
                organization = Organization.objects.create(name=name)
        organizations[name] = organization
    return organizations


def align_branches(report, organizations, *, apply):
    branches = {}
    for org_name, targets in BRANCHES.items():
        organization = organizations.get(org_name)
        if not organization:
            for code, name in targets:
                record(report, "branches", "created", f"{org_name} / {name}")
                branches.setdefault(org_name, []).append(name)
            continue
        for code, name in targets:
            branch = Branch.objects.filter(organization=organization, code=code).first()
            if branch:
                record(report, "branches", "existing", f"{org_name} / {name}")
            else:
                record(report, "branches", "created", f"{org_name} / {name}")
                if apply:
                    branch = Branch.objects.create(organization=organization, code=code, name=name)
            if branch:
                branches.setdefault(org_name, []).append(branch)
    return branches


def align_departments(report, organizations, *, apply):
    for org_name, organization in organizations.items():
        for code, name in DEPARTMENTS:
            if not organization:
                record(report, "departments", "created", f"{org_name} / {name}")
                continue
            department = Department.objects.filter(organization=organization, code=code).first()
            if department:
                record(report, "departments", "existing", f"{org_name} / {name}")
            else:
                record(report, "departments", "created", f"{org_name} / {name}")
                if apply:
                    Department.objects.create(organization=organization, code=code, name=name)


def align_memberships(report, branches, *, apply):
    for membership in UserMembership.objects.select_related("organization", "branch").filter(is_active=True):
        org_name = membership.organization.name
        canonical_branches = branches.get(org_name, [])
        if membership.branch_id:
            record(report, "memberships", "existing", membership_label(membership))
        elif len(canonical_branches) == 1:
            branch = canonical_branches[0]
            branch_name = getattr(branch, "name", branch)
            record(report, "memberships", "updated", membership_label(membership), f"branch={branch_name}")
            if apply:
                membership.branch = branch
                membership.save(update_fields=["branch", "updated_at"])
        elif org_name in BRANCHES:
            record(report, "memberships", "blocked", membership_label(membership), "multiple or missing canonical branches")
        else:
            record(report, "memberships", "skipped", membership_label(membership), "legacy or non-canonical organization")


def record(report, section, status, name, reason=""):
    report[section].append({"status": status.upper(), "name": str(name), "reason": reason})
    report["summary"][status] += 1


def membership_label(membership):
    return f"user_id={membership.user_id} username={membership.user.username} organization={membership.organization.name}"


def write_report(stdout, report):
    stdout.write("RBAC master data seed alignment")
    stdout.write("===============================")
    stdout.write(f"Mode: {report['mode']}")
    summary = report["summary"]
    stdout.write(
        "Summary: "
        f"created={summary['created']}, existing={summary['existing']}, updated={summary['updated']}, "
        f"skipped={summary['skipped']}, blocked={summary['blocked']}"
    )
    for section in ("organizations", "branches", "departments", "memberships"):
        stdout.write("")
        stdout.write(f"{section}:")
        for row in report[section]:
            suffix = f" ({row['reason']})" if row["reason"] else ""
            stdout.write(f"  - {row['status']}: {row['name']}{suffix}")
