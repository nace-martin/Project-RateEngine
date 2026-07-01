import json

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from parties.management.commands.rbac_legacy_organization_cleanup_plan import (
    LEGACY_ORGANIZATIONS,
    QUOTE_SPOT_MODELS,
    TARGET_ORGANIZATION,
    TEST_ORGANIZATION,
    label,
    safe,
)
from parties.models import Branch, Department, Organization

CANONICAL_BRANCH_CODES = {"POM", "LAE", "BNE", "SUV", "HIR"}
CANONICAL_DEPARTMENT_CODES = {"AIR", "SEA", "CUS", "TRN"}


class Command(BaseCommand):
    help = "Read-only plan for consolidating duplicate Branch and Department master data."

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
    branch_rows = [branch_row(branch, target_org) for branch in legacy_duplicates(Branch)]
    department_rows = [department_row(department, target_org) for department in legacy_duplicates(Department)]
    rows = branch_rows + department_rows
    return {
        "write_enabled": False,
        "target_organization": label(target_org),
        "quote_spot_historical_records": {
            "classification": "DEV_TEST_LEGACY",
            "historical_backfill_required": False,
            "mutated_by_cleanup": False,
        },
        "summary": {
            "duplicate_branches": len(branch_rows),
            "duplicate_departments": len(department_rows),
            "dependencies": sum(row["dependency_count"] for row in rows),
            "auto_repointable_dependencies": sum(row["auto_repointable_dependency_count"] for row in rows),
            "blocked_dependencies": sum(row["blocked_dependency_count"] for row in rows),
        },
        "branches": branch_rows,
        "departments": department_rows,
    }


def legacy_duplicates(model):
    return list(
        model.objects.filter(organization__name__in=LEGACY_ORGANIZATIONS, is_active=True)
        .select_related("organization")
        .order_by("organization__name", "code", "id")
    )


def branch_row(branch, target_org):
    target = None
    if target_org is not None and branch.code in CANONICAL_BRANCH_CODES:
        target = Branch.objects.filter(organization=target_org, code=branch.code, is_active=True).exclude(pk=branch.pk).first()
    return duplicate_row(branch, target, Branch)


def department_row(department, target_org):
    target = None
    if target_org is not None and department.code in CANONICAL_DEPARTMENT_CODES:
        target = Department.objects.filter(organization=target_org, code=department.code, is_active=True).exclude(pk=department.pk).first()
    return duplicate_row(department, target, Department)


def duplicate_row(source, target, target_model):
    dependencies = dependency_rows(source, target, target_model)
    blockers = sorted({reason for row in dependencies for reason in row["blockers"]})
    if target is None:
        blockers.append("canonical target missing")
    if source.organization.name == TEST_ORGANIZATION:
        blockers.append("DEV_TEST_LEGACY manual review required")
    dependency_count = sum(row["count"] for row in dependencies)
    auto_count = sum(row["count"] for row in dependencies if row["auto_repointable"])
    return {
        "id": safe(source.pk),
        "organization": safe(source.organization.name),
        "code": safe(source.code),
        "name": safe(source.name),
        "is_active": source.is_active,
        "canonical_target": object_label(target),
        "dependencies": dependencies,
        "dependency_count": dependency_count,
        "auto_repointable_dependency_count": auto_count,
        "blocked_dependency_count": dependency_count - auto_count,
        "blockers": blockers,
        "recommended_action": recommended_action(source, target, dependency_count, blockers, auto_count),
    }


def dependency_rows(source, target, target_model):
    rows = []
    for model in sorted(apps.get_models(), key=lambda item: item._meta.label):
        for field in model._meta.fields:
            if not isinstance(field, models.ForeignKey) or field.remote_field.model is not target_model:
                continue
            queryset = model.objects.filter(**{field.name: source}).order_by("pk")
            count = queryset.count()
            if not count:
                continue
            blockers = dependency_blockers(model, source, target)
            rows.append(
                {
                    "model": model._meta.label,
                    "field": field.name,
                    "count": count,
                    "auto_repointable": not blockers,
                    "target": object_label(target),
                    "blockers": blockers,
                    "sample_ids": [safe(obj.pk) for obj in queryset[:5]],
                }
            )
    return rows


def dependency_blockers(model, source, target):
    blockers = []
    if target is None:
        blockers.append("canonical target missing")
    if source.organization.name == TEST_ORGANIZATION:
        blockers.append("DEV_TEST_LEGACY manual review required")
    if model._meta.label in QUOTE_SPOT_MODELS:
        blockers.append("DEV_TEST_LEGACY quote/SPOT historical record")
    return blockers


def apply_consolidation(*, apply):
    before = build_report()
    actions = []
    for source, target_model in [
        *[(branch, Branch) for branch in legacy_duplicates(Branch)],
        *[(department, Department) for department in legacy_duplicates(Department)],
    ]:
        target = canonical_target(source, target_model)
        row = duplicate_row(source, target, target_model)
        for dep in row["dependencies"]:
            status = "PLANNED" if dep["auto_repointable"] else "BLOCKED"
            if apply and status == "PLANNED":
                model = apps.get_model(dep["model"])
                model.objects.filter(**{dep["field"]: source}).update(**{dep["field"]: target})
                status = "APPLIED"
            actions.append(
                {
                    "master_data_type": target_model._meta.label,
                    "source": object_label(source),
                    "model": dep["model"],
                    "field": dep["field"],
                    "count": dep["count"],
                    "target": dep["target"],
                    "status": status,
                    "blockers": dep["blockers"],
                }
            )
        source.refresh_from_db()
        external_dependencies = external_dependency_count(source, target_model)
        can_deactivate = external_dependencies == 0 and source.is_active and source.organization.name != TEST_ORGANIZATION
        status = "PLANNED" if can_deactivate else "UNCHANGED"
        if apply and can_deactivate:
            source.is_active = False
            source.save(update_fields=["is_active", "updated_at"])
            status = "APPLIED"
        actions.append(
            {
                "master_data_type": target_model._meta.label,
                "source": object_label(source),
                "model": target_model._meta.label,
                "field": "is_active",
                "count": 1,
                "target": None,
                "status": status,
                "blockers": [] if external_dependencies == 0 else [f"dependencies remain: {external_dependencies}"],
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


def canonical_target(source, target_model):
    target_org = Organization.objects.filter(name=TARGET_ORGANIZATION).first()
    if target_org is None:
        return None
    if target_model is Branch and source.code not in CANONICAL_BRANCH_CODES:
        return None
    if target_model is Department and source.code not in CANONICAL_DEPARTMENT_CODES:
        return None
    return target_model.objects.filter(organization=target_org, code=source.code, is_active=True).exclude(pk=source.pk).first()


def external_dependency_count(source, target_model):
    count = 0
    for model in apps.get_models():
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey) and field.remote_field.model is target_model:
                count += model.objects.filter(**{field.name: source}).count()
    return count


def recommended_action(source, target, dependency_count, blockers, auto_count):
    if source.organization.name == TEST_ORGANIZATION:
        return "dev_test_manual_review"
    if dependency_count == 0:
        return "deactivate_after_zero_dependencies"
    if target is None:
        return "manual_review_required"
    if auto_count:
        return "repoint_references"
    if blockers:
        return "manual_review_required"
    return "manual_review_required"


def object_label(value):
    if value is None:
        return None
    org = getattr(value, "organization", None)
    prefix = f"{org.name}:" if org is not None else ""
    return safe(f"{prefix}{value.code} {value.name}")


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC duplicate master data consolidation plan")
    stdout.write("=============================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(
        f"Summary: branches={summary['duplicate_branches']} departments={summary['duplicate_departments']} "
        f"dependencies={summary['dependencies']} auto_repointable={summary['auto_repointable_dependencies']} "
        f"blocked={summary['blocked_dependencies']}"
    )
