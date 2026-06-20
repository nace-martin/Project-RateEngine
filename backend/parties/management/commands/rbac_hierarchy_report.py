import json
from collections import Counter

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from accounts.models import UserMembership
from parties.models import Branch, Department, Organization


INTENDED_OPERATING_ENTITIES = {
    "EFM PNG": {"branches": {"Port Moresby", "Lae"}},
    "EFM Australia": {"branches": {"Brisbane"}},
    "EFM Fiji": {"branches": {"Suva"}},
    "EFM Solomon Islands": {"branches": {"Honiara"}},
}
INTENDED_TENANT = "EFM Group"
EXPECTED_DEPARTMENTS = {
    "Air Freight",
    "Sea Freight",
    "Customs",
    "Transport",
    "Warehousing",
    "EAC",
}


class Command(BaseCommand):
    help = "Read-only diagnostics for the RBAC organization/branch/department hierarchy."

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
            help="Include safe row-level hierarchy details.",
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
        self.stdout.write("RBAC hierarchy validation report")
        self.stdout.write("================================")
        self.stdout.write("Mode: read-only diagnostics")

        model = report["model_assessment"]
        self.stdout.write("")
        self.stdout.write("Model assessment:")
        self.stdout.write(f"  tenant_model_exists={model['tenant_model_exists']}")
        self.stdout.write(f"  organization_role={model['organization_role']}")
        self.stdout.write(f"  can_represent_intended_hierarchy={model['can_represent_intended_hierarchy']}")
        self.stdout.write(f"  recommendation={model['recommendation']}")

        summary = report["summary"]
        self.stdout.write("")
        self.stdout.write(
            "Stored data: "
            f"organizations={summary['organizations']}, "
            f"branches={summary['branches']}, "
            f"departments={summary['departments']}, "
            f"memberships={summary['memberships']}, "
            f"active_memberships={summary['active_memberships']}, "
            f"active_memberships_missing_branch={summary['active_memberships_missing_branch']}"
        )

        self.stdout.write("")
        self.stdout.write("Intended hierarchy:")
        self.stdout.write(f"  tenant={report['intended_hierarchy']['tenant']}")
        for entity, payload in report["intended_hierarchy"]["operating_entities"].items():
            branches = ", ".join(payload["branches"])
            self.stdout.write(f"  - {entity}: branches={branches}")

        self.stdout.write("")
        self.stdout.write("Mismatches:")
        mismatches = report["mismatches"]
        self.stdout.write(f"  missing_operating_entities={mismatches['missing_operating_entities']}")
        self.stdout.write(f"  extra_organizations={mismatches['extra_organizations']}")
        self.stdout.write(f"  missing_branches_by_entity={mismatches['missing_branches_by_entity']}")
        self.stdout.write(f"  branches_under_unexpected_organization={mismatches['branches_under_unexpected_organization']}")
        self.stdout.write(f"  active_memberships_missing_branch={mismatches['active_memberships_missing_branch']}")

        self.stdout.write("")
        self.stdout.write("Answers:")
        for key, value in report["answers"].items():
            self.stdout.write(f"  {key}: {value}")

        for section, rows in report.get("details", {}).items():
            if not rows:
                continue
            self.stdout.write("")
            self.stdout.write(f"{section}:")
            for row in rows:
                self.stdout.write(f"  - {format_detail(row)}")


def build_report(*, show_details=False, limit=50):
    organizations = list(Organization.objects.order_by("name", "id"))
    branches = list(Branch.objects.select_related("organization").order_by("organization__name", "code", "id"))
    departments = list(
        Department.objects.select_related("organization", "branch").order_by("organization__name", "code", "id")
    )
    memberships = list(
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role")
        .order_by("user__username", "organization__name", "id")
    )
    model_assessment = assess_model()
    mismatches = hierarchy_mismatches(organizations, branches, memberships)
    report = {
        "write_enabled": False,
        "intended_hierarchy": intended_hierarchy(),
        "model_assessment": model_assessment,
        "summary": {
            "organizations": len(organizations),
            "active_organizations": sum(1 for org in organizations if org.is_active),
            "branches": len(branches),
            "active_branches": sum(1 for branch in branches if branch.is_active),
            "departments": len(departments),
            "active_departments": sum(1 for department in departments if department.is_active),
            "memberships": len(memberships),
            "active_memberships": sum(1 for membership in memberships if membership.is_active),
            "active_memberships_missing_branch": sum(
                1 for membership in memberships if membership.is_active and membership.branch_id is None
            ),
            "active_memberships_missing_department": sum(
                1 for membership in memberships if membership.is_active and membership.department_id is None
            ),
            "organizations_with_branches": dict(sorted(Counter(branch.organization.name for branch in branches).items())),
            "organizations_with_departments": dict(
                sorted(Counter(department.organization.name for department in departments).items())
            ),
        },
        "records": {
            "organizations": [organization_row(org) for org in organizations],
            "branches": [branch_row(branch) for branch in branches],
            "departments": [department_row(department) for department in departments],
        },
        "membership_summary": membership_summary(memberships),
        "mismatches": mismatches,
        "answers": answers(model_assessment, mismatches),
    }
    if show_details:
        report["details"] = {
            "organizations": [organization_row(org) for org in organizations[:limit]],
            "branches": [branch_row(branch) for branch in branches[:limit]],
            "departments": [department_row(department) for department in departments[:limit]],
            "memberships": [membership_row(membership) for membership in memberships[:limit]],
        }
    return report


def intended_hierarchy():
    return {
        "tenant": INTENDED_TENANT,
        "operating_entities": {
            entity: {"branches": sorted(payload["branches"])}
            for entity, payload in sorted(INTENDED_OPERATING_ENTITIES.items())
        },
        "departments": sorted(EXPECTED_DEPARTMENTS),
    }


def assess_model():
    tenant_models = [
        f"{model._meta.app_label}.{model.__name__}"
        for model in apps.get_models()
        if "tenant" in model.__name__.lower()
    ]
    return {
        "tenant_model_exists": bool(tenant_models),
        "tenant_models": tenant_models,
        "organization_role": (
            "Organization currently acts as the top workspace/operating entity model; "
            "there is no separate EFM Group tenant layer."
        ),
        "branch_role": "Branch is an office/location under exactly one Organization.",
        "department_role": "Department belongs to one Organization and can optionally belong to one Branch.",
        "membership_role": "UserMembership ties user to Organization, optional Branch, optional Department, and Role.",
        "can_represent_intended_hierarchy": False,
        "recommendation": (
            "Do not redesign immediately. Treat Organization as operating entity for now, "
            "document EFM Group as an external/business tenant concept, and consider a Tenant model only "
            "if multi-group SaaS or explicit group-level ownership is required."
        ),
    }


def hierarchy_mismatches(organizations, branches, memberships):
    organization_names = {org.name for org in organizations}
    expected_entities = set(INTENDED_OPERATING_ENTITIES)
    branch_names_by_org = {}
    for branch in branches:
        branch_names_by_org.setdefault(branch.organization.name, set()).add(branch.name)

    missing_entities = sorted(expected_entities - organization_names)
    extra_organizations = sorted(organization_names - expected_entities - {INTENDED_TENANT})
    missing_branches = {}
    for entity, payload in INTENDED_OPERATING_ENTITIES.items():
        missing = sorted(payload["branches"] - branch_names_by_org.get(entity, set()))
        if missing:
            missing_branches[entity] = missing

    expected_branch_names = {
        branch_name
        for payload in INTENDED_OPERATING_ENTITIES.values()
        for branch_name in payload["branches"]
    }
    unexpected_branch_rows = [
        {
            "branch": ascii_safe(branch.name),
            "organization": ascii_safe(branch.organization.name),
        }
        for branch in branches
        if branch.name in expected_branch_names
        and branch.organization.name not in expected_entities
    ]
    active_missing_branch = [
        membership_row(membership)
        for membership in memberships
        if membership.is_active and membership.branch_id is None
    ]
    return {
        "missing_operating_entities": missing_entities,
        "extra_organizations": extra_organizations,
        "missing_branches_by_entity": missing_branches,
        "branches_under_unexpected_organization": unexpected_branch_rows,
        "active_memberships_missing_branch": len(active_missing_branch),
        "active_memberships_missing_branch_examples": active_missing_branch[:10],
        "efm_group_stored_as_organization": INTENDED_TENANT in organization_names,
    }


def answers(model_assessment, mismatches):
    no_tenant = not model_assessment["tenant_model_exists"]
    return {
        "is_there_a_tenant_model": "yes" if not no_tenant else "no",
        "organization_currently_acts_as": "operating entity/workspace, not a separate EFM Group tenant",
        "are_efm_operating_entities_represented_as_organizations": yes_no(not mismatches["missing_operating_entities"]),
        "are_expected_offices_represented_as_branches": yes_no(not mismatches["missing_branches_by_entity"]),
        "are_branches_tied_to_exactly_one_organization": "yes; Branch.organization is a required ForeignKey",
        "are_departments_tied_to_organization_and_optionally_branch": "yes; Department.organization is required and Department.branch is nullable",
        "are_active_memberships_missing_branch": yes_no(mismatches["active_memberships_missing_branch"] > 0),
        "why_branch_readiness_is_low": (
            "Branch model/master data exists only where seeded, but customer/CRM/quote records and active memberships "
            "are not consistently populated with branch."
        ),
        "recommended_next_step": (
            "Confirm branch master data under operating entities, populate active user memberships with branch, "
            "then rerun branch source diagnostics before historical backfill."
        ),
    }


def membership_summary(memberships):
    by_org = Counter()
    missing = {
        "branch": 0,
        "department": 0,
    }
    for membership in memberships:
        if not membership.is_active:
            continue
        by_org[membership.organization.name] += 1
        if membership.branch_id is None:
            missing["branch"] += 1
        if membership.department_id is None:
            missing["department"] += 1
    return {
        "active_by_organization": dict(sorted(by_org.items())),
        "active_missing_branch": missing["branch"],
        "active_missing_department": missing["department"],
    }


def organization_row(organization):
    return {
        "id": str(organization.pk),
        "name": ascii_safe(organization.name),
        "slug": ascii_safe(organization.slug),
        "is_active": organization.is_active,
    }


def branch_row(branch):
    return {
        "id": str(branch.pk),
        "name": ascii_safe(branch.name),
        "code": ascii_safe(branch.code),
        "organization": scope_label(branch.organization),
        "is_active": branch.is_active,
    }


def department_row(department):
    return {
        "id": str(department.pk),
        "name": ascii_safe(department.name),
        "code": ascii_safe(department.code),
        "organization": scope_label(department.organization),
        "branch": scope_label(department.branch),
        "is_active": department.is_active,
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
        "is_primary": membership.is_primary,
        "is_active": membership.is_active,
    }


def scope_label(value):
    if value is None:
        return None
    name = getattr(value, "name", None) or getattr(value, "code", None) or str(value)
    return ascii_safe(f"{value.pk}:{name}")


def ascii_safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")


def yes_no(value):
    return "yes" if value else "no"


def format_detail(row):
    return ", ".join(f"{key}={value if value is not None else '-'}" for key, value in row.items())
