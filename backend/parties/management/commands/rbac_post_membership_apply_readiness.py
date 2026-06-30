import json
from collections import Counter
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from accounts.models import CustomUser, UserMembership
from parties.models import Branch, Department, OperatingEntity, Organization


ROOT = Path(__file__).resolve().parents[4]
CANONICAL_ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
CANONICAL_TOP_ORGANIZATIONS = ("Express Freight Management",)
CANONICAL_OPERATING_ENTITIES = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
CANONICAL_BRANCHES = {
    "EFM PNG": ("Port Moresby", "Lae"),
    "EFM Australia": ("Brisbane",),
    "EFM Fiji": ("Suva",),
    "EFM Solomon Islands": ("Honiara",),
}
CANONICAL_DEPARTMENTS = ("Air Freight", "Sea Freight", "Customs", "Transport")
LEGACY_EAC_NAMES = ("EAC", "EFM Express Air Cargo", "Express Air Cargo")
STALE_ARTIFACTS = (
    "backend/parties/management/commands/rbac_hierarchy_tooling_alignment_audit.py",
    "docs/beta-readiness-efm.md",
    "docs/tenant-model-beta.md",
    "docs/rbac-organisation-audit-plan.md",
)


class Command(BaseCommand):
    help = "Read-only RBAC readiness diagnostics after membership reassignment apply."

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
    organizations = {
        org.name: org
        for org in Organization.objects.filter(name__in=CANONICAL_TOP_ORGANIZATIONS + CANONICAL_ORGANIZATIONS)
        .filter(is_active=True)
    }
    operating_entities = list(
        OperatingEntity.objects.select_related("organization").filter(
            organization__name__in=CANONICAL_TOP_ORGANIZATIONS,
            name__in=CANONICAL_OPERATING_ENTITIES,
        )
    )
    branches = list(
        Branch.objects.select_related("organization", "operating_entity").filter(
            organization__name__in=CANONICAL_TOP_ORGANIZATIONS,
            is_active=True,
        )
    )
    departments = list(
        Department.objects.select_related("organization").filter(
            organization__name__in=CANONICAL_TOP_ORGANIZATIONS + CANONICAL_ORGANIZATIONS
        )
    )
    memberships = list(
        UserMembership.objects.select_related("user", "organization", "operating_entity", "branch", "department", "role")
        .filter(is_active=True)
        .order_by("user__username", "id")
    )
    active_users = list(CustomUser.objects.filter(is_active=True).order_by("username", "id"))

    canonical = canonical_report(organizations, operating_entities, branches, departments)
    membership = membership_report(memberships, active_users)
    legacy = legacy_report()
    stale_artifacts = stale_artifact_report()
    blockers = blockers_for(canonical, membership)
    final_blockers = final_blockers_for(canonical, membership, legacy, stale_artifacts)
    return {
        "write_enabled": False,
        "canonical": canonical,
        "memberships": membership,
        "legacy": legacy,
        "stale_artifacts": stale_artifacts,
        "readiness": {
            "status": "READY_FOR_BACKFILL_PLANNING" if not blockers else "NOT_READY_FOR_BACKFILL_PLANNING",
            "blockers": blockers,
        },
        "final_readiness": {
            "status": "READY" if not final_blockers else "NOT_READY",
            "blockers": final_blockers,
            "notes": [
                "country-as-organization assumptions are obsolete",
                "EAC is legacy Air Freight wording only",
                "Quote/SPOT historical records remain DEV_TEST_LEGACY; no historical backfill is planned",
            ],
        },
    }


def canonical_report(organizations, operating_entities, branches, departments):
    branch_names_by_entity = {}
    for branch in branches:
        key = branch.operating_entity.name if branch.operating_entity else branch.organization.name
        branch_names_by_entity.setdefault(key, set()).add(branch.name)
    department_names_by_org = {}
    for department in departments:
        department_names_by_org.setdefault(department.organization.name, set()).add(department.name)
    missing_branches = {
        entity_name: [name for name in branch_names if name not in branch_names_by_entity.get(entity_name, set())]
        for entity_name, branch_names in CANONICAL_BRANCHES.items()
    }
    missing_departments = {
        org_name: [name for name in CANONICAL_DEPARTMENTS if name not in department_names_by_org.get(org_name, set())]
        for org_name in (CANONICAL_TOP_ORGANIZATIONS if any(name in organizations for name in CANONICAL_TOP_ORGANIZATIONS) else CANONICAL_ORGANIZATIONS)
    }
    entity_names = {entity.name for entity in operating_entities}
    duplicate_codes = duplicate_codes_for(organizations.values(), operating_entities, branches, departments)
    branches_with_operating_entity = sum(1 for branch in branches if branch.operating_entity_id)
    return {
        "organizations_present": sorted(organizations),
        "organizations_missing": [name for name in CANONICAL_TOP_ORGANIZATIONS if name not in organizations],
        "organization_completeness": {
            "present": len([name for name in CANONICAL_TOP_ORGANIZATIONS if name in organizations]),
            "expected": len(CANONICAL_TOP_ORGANIZATIONS),
            "ready": all(name in organizations for name in CANONICAL_TOP_ORGANIZATIONS),
        },
        "operating_entities_present": sorted(entity_names),
        "operating_entities_missing": [name for name in CANONICAL_OPERATING_ENTITIES if name not in entity_names],
        "operating_entity_completeness": {
            "present": len(entity_names),
            "expected": len(CANONICAL_OPERATING_ENTITIES),
            "ready": all(name in entity_names for name in CANONICAL_OPERATING_ENTITIES),
        },
        "branches_missing": {org: names for org, names in missing_branches.items() if names},
        "branches_missing_operating_entity": [branch_row(branch) for branch in branches if branch.operating_entity_id is None],
        "branch_operating_entity_completeness": {
            "total": len(branches),
            "with_operating_entity": branches_with_operating_entity,
            "missing_operating_entity": len(branches) - branches_with_operating_entity,
            "ready": bool(branches) and branches_with_operating_entity == len(branches),
        },
        "operating_entities_without_branches": sorted(
            entity.name for entity in operating_entities if entity.name not in branch_names_by_entity
        ),
        "duplicate_codes": duplicate_codes,
        "orphaned_branches": [branch_row(branch) for branch in branches if branch.organization.name not in CANONICAL_TOP_ORGANIZATIONS],
        "departments_missing": {org: names for org, names in missing_departments.items() if names},
    }


def duplicate_codes_for(organizations, operating_entities, branches, departments):
    return {
        "organizations": duplicates(org.slug for org in organizations),
        "operating_entities": duplicates(f"{entity.organization_id}:{entity.code}" for entity in operating_entities),
        "branches": duplicates(f"{branch.organization_id}:{branch.code}" for branch in branches),
        "departments": duplicates(f"{department.organization_id}:{department.code}" for department in departments),
    }


def duplicates(values):
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def membership_report(memberships, active_users):
    canonical_orgs = set(CANONICAL_TOP_ORGANIZATIONS + CANONICAL_ORGANIZATIONS)
    memberships_by_user = {}
    for membership in memberships:
        memberships_by_user.setdefault(membership.user_id, []).append(membership)
    active_user_ids = {user.id for user in active_users}
    no_membership_users = [user_row(user) for user in active_users if user.id not in memberships_by_user]
    multiple_membership_users = [
        user_row(memberships_for_user[0].user)
        for user_id, memberships_for_user in memberships_by_user.items()
        if user_id in active_user_ids and len(memberships_for_user) > 1
    ]
    missing_operating_entity = [membership for membership in memberships if membership.operating_entity_id is None]
    inferable_from_branch = [
        membership for membership in missing_operating_entity if membership.branch_id and membership.branch.operating_entity_id
    ]
    not_inferable = [membership for membership in missing_operating_entity if membership not in inferable_from_branch]
    return {
        "active_users": len(active_users),
        "active_memberships": len(memberships),
        "complete_canonical_memberships": sum(1 for membership in memberships if membership_is_complete_canonical(membership)),
        "membership_operating_entity_completeness": {
            "total": len(memberships),
            "with_operating_entity": len(memberships) - len(missing_operating_entity),
            "missing_operating_entity": len(missing_operating_entity),
            "ready": len(not_inferable) == 0,
        },
        "missing_organization": sum(1 for membership in memberships if membership.organization_id is None),
        "missing_branch": sum(1 for membership in memberships if membership.branch_id is None),
        "memberships_missing_operating_entity": len(missing_operating_entity),
        "memberships_inferable_from_branch": len(inferable_from_branch),
        "memberships_not_inferable": len(not_inferable),
        "scope_resolution_operating_entity_ready": len(not_inferable) == 0,
        "missing_operating_entity": len(missing_operating_entity),
        "missing_department": sum(1 for membership in memberships if membership.department_id is None),
        "missing_role": sum(1 for membership in memberships if membership.role_id is None),
        "legacy_non_canonical_organization_memberships": sum(
            1 for membership in memberships if membership.organization and membership.organization.name not in canonical_orgs
        ),
        "users_with_no_active_membership": len(no_membership_users),
        "users_with_multiple_active_memberships": len(multiple_membership_users),
        "no_active_membership_examples": no_membership_users[:10],
        "multiple_active_membership_examples": multiple_membership_users[:10],
        "active_memberships_by_status": dict(sorted(Counter(membership_status(membership) for membership in memberships).items())),
    }


def membership_is_complete_canonical(membership):
    return (
        membership.organization
        and membership.organization.name in CANONICAL_TOP_ORGANIZATIONS + CANONICAL_ORGANIZATIONS
        and membership.branch_id
        and membership.department_id
        and membership.role_id
    )


def membership_status(membership):
    if not membership.organization_id:
        return "missing_organization"
    if membership.organization.name not in CANONICAL_TOP_ORGANIZATIONS + CANONICAL_ORGANIZATIONS:
        return "legacy_organization"
    if not membership.operating_entity_id:
        if membership.branch_id and membership.branch.operating_entity_id:
            return "operating_entity_inferable_from_branch"
        return "missing_operating_entity"
    if not membership.branch_id:
        return "missing_branch"
    if not membership.department_id:
        return "missing_department"
    if not membership.role_id:
        return "missing_role"
    return "complete_canonical"


def legacy_report():
    return {
        "country_as_organization_dependencies": dependency_report(CANONICAL_ORGANIZATIONS),
        "eac_legacy_references": dependency_report(LEGACY_EAC_NAMES),
        "quote_spot_historical_records": quote_spot_legacy_report(),
    }


def dependency_report(names):
    organizations = list(Organization.objects.filter(name__in=names).order_by("name"))
    active_names = [org.name for org in organizations if org.is_active]
    rows = []
    active_rows = []
    for model in sorted(apps.get_models(), key=lambda item: item._meta.label):
        for field in model._meta.fields:
            if not isinstance(field, models.ForeignKey):
                continue
            target = field.remote_field.model
            if target is Organization:
                filters = {f"{field.name}__name__in": names}
            elif target is Branch:
                filters = {f"{field.name}__organization__name__in": names}
            elif target is Department:
                filters = {f"{field.name}__organization__name__in": names}
            else:
                continue
            count = model.objects.filter(**filters).count()
            if count:
                rows.append({"model": model._meta.label, "field": field.name, "count": count})
            if active_names:
                active_filters = dict(filters)
                if target is Organization:
                    active_filters[f"{field.name}__name__in"] = active_names
                elif target is Branch:
                    active_filters[f"{field.name}__organization__name__in"] = active_names
                elif target is Department:
                    active_filters[f"{field.name}__organization__name__in"] = active_names
                active_count = model.objects.filter(**active_filters).count()
                if active_count:
                    active_rows.append({"model": model._meta.label, "field": field.name, "count": active_count})
    total = sum(row["count"] for row in rows)
    active_total = sum(row["count"] for row in active_rows)
    return {
        "organization_names": [safe(org.name) for org in organizations],
        "organization_count": len(organizations),
        "active_organization_names": [safe(name) for name in active_names],
        "active_organization_count": len(active_names),
        "dependency_count": total,
        "active_dependency_count": active_total,
        "dependencies": rows,
        "active_dependencies": active_rows,
        "ready_for_deactivation_review": len(organizations) > 0 and total == 0,
        "inactive_or_dependency_free": all((not org.is_active) or dependency_count_for_single_org(org) == 0 for org in organizations),
        "rollback_mapping_required": len(organizations) > 0,
    }


def quote_spot_legacy_report():
    quote_model = apps.get_model("quotes", "Quote")
    spot_model = apps.get_model("quotes", "SpotPricingEnvelopeDB")
    return {
        "classification": "DEV_TEST_LEGACY",
        "historical_backfill_required": False,
        "build_historical_backfill_tooling": False,
        "quote_count": quote_model.objects.count(),
        "spot_count": spot_model.objects.count(),
    }


def stale_artifact_report():
    rows = []
    for relative_path in STALE_ARTIFACTS:
        source = read_source(relative_path)
        rows.append(
            {
                "path": relative_path,
                "exists": source is not None,
                "mentions_country_as_organization": bool(source and all(name in source for name in CANONICAL_ORGANIZATIONS)),
                "mentions_legacy_eac": bool(source and any(name in source for name in LEGACY_EAC_NAMES)),
                "status": "superseded_legacy_reference",
                "note": "country-as-organization assumptions are obsolete; EAC is legacy Air Freight wording only",
            }
        )
    return rows


def read_source(relative_path):
    path = ROOT / relative_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def blockers_for(canonical, membership):
    blockers = []
    if canonical["organizations_missing"]:
        blockers.append(f"missing canonical organization: {canonical['organizations_missing']}")
    if canonical["operating_entities_missing"]:
        blockers.append(f"missing operating entities: {canonical['operating_entities_missing']}")
    if canonical["branches_missing"]:
        blockers.append(f"missing canonical branches: {canonical['branches_missing']}")
    if canonical["branches_missing_operating_entity"]:
        blockers.append(f"branches_missing_operating_entity: {len(canonical['branches_missing_operating_entity'])}")
    if canonical["operating_entities_without_branches"]:
        blockers.append(f"operating_entities_without_branches: {canonical['operating_entities_without_branches']}")
    if any(canonical["duplicate_codes"].values()):
        blockers.append(f"duplicate_codes: {canonical['duplicate_codes']}")
    if canonical["departments_missing"]:
        blockers.append(f"missing canonical departments: {canonical['departments_missing']}")
    for key in ("legacy_non_canonical_organization_memberships", "missing_organization", "memberships_not_inferable", "missing_branch", "missing_department", "missing_role", "users_with_no_active_membership", "users_with_multiple_active_memberships"):
        if membership[key]:
            blockers.append(f"{key}: {membership[key]}")
    return blockers


def final_blockers_for(canonical, membership, legacy, stale_artifacts):
    blockers = blockers_for(canonical, membership)
    country_dependencies = legacy["country_as_organization_dependencies"]["active_dependency_count"]
    eac_dependencies = legacy["eac_legacy_references"]["active_dependency_count"]
    if country_dependencies:
        blockers.append(f"active_legacy_country_as_organization_dependencies: {country_dependencies}")
    if eac_dependencies:
        blockers.append(f"active_eac_legacy_references: {eac_dependencies}")
    return blockers


def user_row(user):
    return {
        "user_id": str(user.id),
        "username": safe(user.username),
        "email": safe(user.email),
    }


def branch_row(branch):
    return {
        "id": str(branch.id),
        "name": safe(branch.name),
        "code": safe(branch.code),
        "organization": safe(branch.organization.name),
        "operating_entity": safe(branch.operating_entity.name) if branch.operating_entity else None,
    }


def dependency_count_for_single_org(org):
    total = 0
    for model in apps.get_models():
        for field in model._meta.fields:
            if not isinstance(field, models.ForeignKey):
                continue
            target = field.remote_field.model
            if target is Organization:
                filters = {field.name: org}
            elif target is Branch:
                filters = {f"{field.name}__organization": org}
            elif target is Department:
                filters = {f"{field.name}__organization": org}
            else:
                continue
            total += model.objects.filter(**filters).count()
    return total


def write_text(stdout, report):
    readiness = report["readiness"]
    canonical = report["canonical"]
    membership = report["memberships"]
    stdout.write("RBAC post-membership-apply readiness")
    stdout.write("====================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Readiness: {readiness['status']}")
    stdout.write(f"Final readiness: {report['final_readiness']['status']}")
    stdout.write("")
    stdout.write("Canonical master data:")
    stdout.write(f"  organization_completeness={canonical['organization_completeness']}")
    stdout.write(f"  operating_entity_completeness={canonical['operating_entity_completeness']}")
    stdout.write(f"  organizations_missing={canonical['organizations_missing']}")
    stdout.write(f"  operating_entities_missing={canonical['operating_entities_missing']}")
    stdout.write(f"  branches_missing={canonical['branches_missing']}")
    stdout.write(f"  branches_missing_operating_entity={len(canonical['branches_missing_operating_entity'])}")
    stdout.write(f"  branch_operating_entity_completeness={canonical['branch_operating_entity_completeness']}")
    stdout.write(f"  operating_entities_without_branches={canonical['operating_entities_without_branches']}")
    stdout.write(f"  duplicate_codes={canonical['duplicate_codes']}")
    stdout.write(f"  orphaned_branches={len(canonical['orphaned_branches'])}")
    stdout.write(f"  departments_missing={canonical['departments_missing']}")
    stdout.write("")
    stdout.write(
        "Memberships: "
        f"active_users={membership['active_users']}, "
        f"active_memberships={membership['active_memberships']}, "
        f"complete_canonical={membership['complete_canonical_memberships']}, "
        f"membership_operating_entity_completeness={membership['membership_operating_entity_completeness']}, "
        f"missing_org={membership['missing_organization']}, "
        f"memberships_missing_operating_entity={membership['memberships_missing_operating_entity']}, "
        f"memberships_inferable_from_branch={membership['memberships_inferable_from_branch']}, "
        f"memberships_not_inferable={membership['memberships_not_inferable']}, "
        f"scope_resolution_operating_entity_ready={membership['scope_resolution_operating_entity_ready']}, "
        f"missing_branch={membership['missing_branch']}, "
        f"missing_department={membership['missing_department']}, "
        f"missing_role={membership['missing_role']}, "
        f"legacy_org_memberships={membership['legacy_non_canonical_organization_memberships']}, "
        f"users_no_membership={membership['users_with_no_active_membership']}, "
        f"users_multiple_memberships={membership['users_with_multiple_active_memberships']}"
    )
    stdout.write(f"  by_status={membership['active_memberships_by_status']}")
    legacy = report["legacy"]
    stdout.write("")
    stdout.write(
        "Legacy dependencies: "
        f"country_as_organization={legacy['country_as_organization_dependencies']['dependency_count']}, "
        f"eac_legacy_references={legacy['eac_legacy_references']['dependency_count']}, "
        f"quote_spot={legacy['quote_spot_historical_records']['classification']}"
    )
    stdout.write(f"Stale artifacts={len(report['stale_artifacts'])}")
    if readiness["blockers"]:
        stdout.write("")
        stdout.write("Blockers:")
        for blocker in readiness["blockers"]:
            stdout.write(f"  - {blocker}")
    if report["final_readiness"]["blockers"]:
        stdout.write("")
        stdout.write("Final blockers:")
        for blocker in report["final_readiness"]["blockers"]:
            stdout.write(f"  - {blocker}")


def safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")
