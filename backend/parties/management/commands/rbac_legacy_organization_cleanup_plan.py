import json

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from parties.models import Branch, Department, OperatingEntity, Organization


TARGET_ORGANIZATION = "Express Freight Management"
COUNTRY_ORGANIZATIONS = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
LEGACY_EAC_NAMES = ("EFM Express Air Cargo", "EAC", "Express Air Cargo")
TEST_ORGANIZATION = "Test Org"
LEGACY_ORGANIZATIONS = COUNTRY_ORGANIZATIONS + ("EFM Express Air Cargo", TEST_ORGANIZATION)
QUOTE_SPOT_MODELS = {"quotes.Quote", "quotes.SpotPricingEnvelopeDB"}


class Command(BaseCommand):
    help = "Read-only plan for legacy Organization cleanup after OperatingEntity redesign."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    target_org = Organization.objects.filter(name=TARGET_ORGANIZATION).first()
    legacy_orgs = list(Organization.objects.filter(name__in=LEGACY_ORGANIZATIONS).order_by("name", "id"))
    rows = [organization_row(org, target_org) for org in legacy_orgs]
    return {
        "write_enabled": False,
        "target_organization": label(target_org),
        "quote_spot_historical_records": {
            "classification": "DEV_TEST_LEGACY",
            "historical_backfill_required": False,
            "mutated_by_cleanup": False,
        },
        "summary": {
            "organizations": len(rows),
            "dependencies": sum(row["dependency_count"] for row in rows),
            "auto_migratable_dependencies": sum(row["auto_migratable_dependency_count"] for row in rows),
            "blocked_dependencies": sum(row["blocked_dependency_count"] for row in rows),
        },
        "organizations": rows,
    }


def organization_row(org, target_org):
    dependencies = dependency_rows(org, target_org)
    blockers = sorted({reason for row in dependencies for reason in row["blockers"]})
    dependency_count = sum(row["count"] for row in dependencies)
    auto_count = sum(row["count"] for row in dependencies if row["auto_migratable"])
    blocked_count = dependency_count - auto_count
    return {
        "id": str(org.id),
        "name": safe(org.name),
        "slug": safe(org.slug),
        "is_active": org.is_active,
        "classification": classify_organization(org.name),
        "dependencies": dependencies,
        "dependency_count": dependency_count,
        "auto_migratable_dependency_count": auto_count,
        "blocked_dependency_count": blocked_count,
        "target_organization": label(target_org),
        "target_operating_entity": target_operating_entity_name(org.name, target_org),
        "target_branch": None,
        "target_department": "Air Freight" if org.name in LEGACY_EAC_NAMES else None,
        "blockers": blockers,
        "recommended_action": recommended_action(org.name, dependency_count, blockers, auto_count),
    }


def dependency_rows(org, target_org):
    rows = []
    for model in sorted(apps.get_models(), key=lambda item: item._meta.label):
        for field in model._meta.fields:
            if not isinstance(field, models.ForeignKey):
                continue
            if field.remote_field.model not in (Organization, Branch, Department):
                continue
            filters = dependency_filter(field, org)
            if filters is None:
                continue
            queryset = model.objects.filter(**filters).order_by("pk")
            if model in (Branch, Department) and field.name == "organization":
                queryset = queryset.filter(is_active=True)
            count = queryset.count()
            if not count:
                continue
            plan = field_plan(model, field, org, target_org)
            rows.append(
                {
                    "model": model._meta.label,
                    "field": field.name,
                    "target_type": field.remote_field.model._meta.label,
                    "count": count,
                    "auto_migratable": plan["auto_migratable"],
                    "target_organization": label(target_org) if plan["target_organization"] else None,
                    "target_operating_entity": label(plan["target_operating_entity"]),
                    "target_branch": label(plan["target_branch"]),
                    "target_department": label(plan["target_department"]),
                    "blockers": plan["blockers"],
                    "sample_ids": [safe(obj.pk) for obj in queryset[:5]],
                }
            )
    return rows


def dependency_filter(field, org):
    target = field.remote_field.model
    if target is Organization:
        return {field.name: org}
    if target is Branch:
        return {f"{field.name}__organization": org}
    if target is Department:
        return {f"{field.name}__organization": org}
    return None


def field_plan(model, field, org, target_org):
    target = field.remote_field.model
    blockers = []
    target_entity = infer_operating_entity(org, target_org)
    target_branch = None
    target_department = None

    if target_org is None:
        blockers.append("target organization missing")
    if isinstance(field, models.OneToOneField):
        blockers.append("one-to-one dependency requires manual review")
    if org.name == TEST_ORGANIZATION:
        blockers.append("DEV_TEST_LEGACY manual review required")
    if model._meta.label in QUOTE_SPOT_MODELS:
        blockers.append("DEV_TEST_LEGACY quote/SPOT historical record")

    if target is Organization:
        target_department = eac_air_freight_department(org, target_org)
        if org.name in COUNTRY_ORGANIZATIONS and target_entity is None:
            blockers.append("target operating_entity missing")
        if model is Branch:
            blockers.extend(branch_reparent_blockers(org, target_org))
        if model is Department:
            blockers.extend(department_reparent_blockers(org, target_org))
    elif target is Branch:
        target_branch = canonical_branch_for_legacy_field(field, org, target_org)
        target_entity = getattr(target_branch, "operating_entity", None) or target_entity
        if target_branch is None:
            blockers.append("target branch not inferable")
    elif target is Department:
        target_department = canonical_department_for_legacy_field(field, org, target_org)
        if target_department is None:
            blockers.append("target department not inferable")

    return {
        "auto_migratable": not blockers and target_org is not None,
        "target_organization": target_org,
        "target_operating_entity": target_entity,
        "target_branch": target_branch,
        "target_department": target_department,
        "blockers": blockers,
    }


def apply_cleanup(*, apply):
    before = build_report()
    actions = []
    with_orgs = Organization.objects.filter(name__in=LEGACY_ORGANIZATIONS).order_by("name", "id")
    target_org = Organization.objects.filter(name=TARGET_ORGANIZATION).first()
    for org in with_orgs:
        for action in planned_updates_for_org(org, target_org):
            if apply and action["status"] == "PLANNED":
                action["apply"]()
                action["status"] = "APPLIED"
            action.pop("apply", None)
            actions.append(action)
    for org in with_orgs:
        row = organization_row(org, target_org)
        remaining = row["dependency_count"]
        can_deactivate = remaining == 0 or can_deactivate_with_remaining_blockers(row)
        status = "UNCHANGED"
        if can_deactivate and org.is_active:
            status = "APPLIED" if apply else "PLANNED"
            if apply:
                org.is_active = False
                org.save(update_fields=["is_active", "updated_at"])
        actions.append(
            {
                "organization": safe(org.name),
                "model": "parties.Organization",
                "field": "is_active",
                "count": 1,
                "status": status if can_deactivate else "BLOCKED",
                "blockers": [] if can_deactivate else [f"dependencies remain: {remaining}"],
            }
        )
    after = build_report()
    return {
        "mode": "apply" if apply else "dry-run",
        "write_enabled": bool(apply),
        "before": before["summary"],
        "after": after["summary"],
        "summary": {
            "planned": sum(1 for action in actions if action["status"] == "PLANNED"),
            "applied": sum(1 for action in actions if action["status"] == "APPLIED"),
            "unchanged": sum(1 for action in actions if action["status"] == "UNCHANGED"),
            "blocked": sum(1 for action in actions if action["status"] == "BLOCKED"),
        },
        "actions": actions,
    }


def planned_updates_for_org(org, target_org):
    actions = []
    for model in sorted(apps.get_models(), key=lambda item: item._meta.label):
        for field in model._meta.fields:
            if not isinstance(field, models.ForeignKey):
                continue
            if field.remote_field.model not in (Organization, Branch, Department):
                continue
            plan = field_plan(model, field, org, target_org)
            filters = dependency_filter(field, org)
            if filters is None:
                continue
            queryset = model.objects.filter(**filters)
            if model in (Branch, Department) and field.name == "organization":
                queryset = queryset.filter(is_active=True)
            count = queryset.count()
            if not count:
                continue
            status = "PLANNED" if plan["auto_migratable"] else "BLOCKED"
            actions.append(
                {
                    "organization": safe(org.name),
                    "model": model._meta.label,
                    "field": field.name,
                    "count": count,
                    "status": status,
                    "blockers": plan["blockers"],
                    "apply": updater(queryset, model, field, plan),
                }
            )
    return actions


def updater(queryset, model, field, plan):
    def run():
        update = {}
        if field.remote_field.model is Organization:
            update[field.name] = plan["target_organization"]
        elif field.remote_field.model is Branch:
            update[field.name] = plan["target_branch"]
        elif field.remote_field.model is Department:
            update[field.name] = plan["target_department"]
        if has_field(model, "organization"):
            update["organization"] = plan["target_organization"]
        if has_field(model, "operating_entity") and plan["target_operating_entity"] is not None:
            update["operating_entity"] = plan["target_operating_entity"]
        queryset.update(**{name: value for name, value in update.items() if value is not None})

    return run


def dependency_count_for_org(org):
    total = 0
    for model in apps.get_models():
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey) and field.remote_field.model in (Organization, Branch, Department):
                filters = dependency_filter(field, org)
                if filters:
                    total += model.objects.filter(**filters).count()
    return total


def can_deactivate_with_remaining_blockers(row):
    if row["name"] == TEST_ORGANIZATION or row["auto_migratable_dependency_count"]:
        return False
    if row["classification"] not in {"legacy_country_as_organization", "legacy_air_freight_wording"}:
        return False
    allowed = {
        "DEV_TEST_LEGACY quote/SPOT historical record",
        "one-to-one dependency requires manual review",
    }
    return all(
        reason in allowed
        or reason.startswith("target branch code collision:")
        or reason.startswith("target department code collision:")
        for reason in row["blockers"]
    )


def infer_operating_entity(org, target_org):
    if target_org is None or org.name not in COUNTRY_ORGANIZATIONS:
        return None
    return OperatingEntity.objects.filter(organization=target_org, name=org.name).first()


def canonical_branch_for_legacy_field(field, org, target_org):
    sample = field.model.objects.filter(**dependency_filter(field, org)).select_related(field.name).first()
    branch = getattr(sample, field.name, None)
    if branch is None or target_org is None:
        return None
    return Branch.objects.filter(organization=target_org, name=branch.name).first()


def canonical_department_for_legacy_field(field, org, target_org):
    sample = field.model.objects.filter(**dependency_filter(field, org)).select_related(field.name).first()
    department = getattr(sample, field.name, None)
    if department is None or target_org is None:
        return None
    return Department.objects.filter(organization=target_org, name=department.name).first()


def eac_air_freight_department(org, target_org):
    if org.name not in LEGACY_EAC_NAMES or target_org is None:
        return None
    return Department.objects.filter(organization=target_org, name="Air Freight").first()


def branch_reparent_blockers(org, target_org):
    blockers = []
    for branch in Branch.objects.filter(organization=org, is_active=True):
        if Branch.objects.filter(organization=target_org, code=branch.code).exclude(pk=branch.pk).exists():
            blockers.append(f"target branch code collision: {branch.code}")
    return blockers


def department_reparent_blockers(org, target_org):
    blockers = []
    for department in Department.objects.filter(organization=org, is_active=True):
        if Department.objects.filter(organization=target_org, code=department.code).exclude(pk=department.pk).exists():
            blockers.append(f"target department code collision: {department.code}")
    return blockers


def has_field(model, name):
    return any(field.name == name for field in model._meta.fields)


def target_operating_entity_name(name, target_org):
    entity = infer_operating_entity(type("OrgName", (), {"name": name})(), target_org)
    return label(entity)


def classify_organization(name):
    if name in COUNTRY_ORGANIZATIONS:
        return "legacy_country_as_organization"
    if name in LEGACY_EAC_NAMES:
        return "legacy_air_freight_wording"
    if name == TEST_ORGANIZATION:
        return "DEV_TEST_LEGACY"
    return "manual_review"


def recommended_action(name, dependency_count, blockers, auto_count):
    if dependency_count == 0:
        return "dev_test_delete_candidate" if name == TEST_ORGANIZATION else "deactivate_after_zero_dependencies"
    if name == TEST_ORGANIZATION:
        return "manual_review_required"
    if blockers:
        return "manual_review_required"
    if auto_count:
        return "migrate_references"
    return "manual_review_required"


def label(value):
    if value is None:
        return None
    return safe(getattr(value, "name", value))


def safe(value):
    if value is None:
        return None
    return str(value).encode("ascii", "replace").decode("ascii")


def write_text(stdout, report):
    stdout.write("RBAC legacy organization cleanup plan")
    stdout.write("=====================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Target organization: {report['target_organization']}")
    summary = report["summary"]
    stdout.write(
        f"Summary: organizations={summary['organizations']} dependencies={summary['dependencies']} "
        f"auto_migratable={summary['auto_migratable_dependencies']} blocked={summary['blocked_dependencies']}"
    )
    for org in report["organizations"]:
        stdout.write(
            f"- {org['name']} action={org['recommended_action']} deps={org['dependency_count']} "
            f"blocked={org['blocked_dependency_count']}"
        )
