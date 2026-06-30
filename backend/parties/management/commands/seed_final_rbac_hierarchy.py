from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import transaction
from django.db import models

from parties.models import Branch, Department, OperatingEntity, Organization


TARGET_ORGANIZATION = "Express Freight Management"
BRANCHES = {
    "EFM PNG": (("POM", "Port Moresby"), ("LAE", "Lae")),
    "EFM Australia": (("BNE", "Brisbane"),),
    "EFM Fiji": (("SUV", "Suva"),),
    "EFM Solomon Islands": (("HIR", "Honiara"),),
}
DEPARTMENTS = (("AIR", "Air Freight"), ("SEA", "Sea Freight"), ("CUS", "Customs"), ("TRN", "Transport"))


class Command(BaseCommand):
    help = "Idempotently seed final RBAC Branch and Department master data under Express Freight Management."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            report = seed(dry_run=dry_run)
            if dry_run:
                transaction.set_rollback(True)
        self.stdout.write(
            "Final RBAC hierarchy seed complete: "
            f"created={report['created']}, updated={report['updated']}, existing={report['existing']}, "
            f"deactivated={report['deactivated']}, blocked={report['blocked']}, "
            f"missing_operating_entities={report['missing_operating_entities']}"
        )


def seed(*, dry_run=False):
    organization = Organization.objects.get(name=TARGET_ORGANIZATION)
    report = {"created": 0, "updated": 0, "existing": 0, "deactivated": 0, "blocked": 0, "missing_operating_entities": 0}
    canonical_codes = {code for branches in BRANCHES.values() for code, _name in branches}
    for entity_name, branches in BRANCHES.items():
        entity = OperatingEntity.objects.filter(organization=organization, name=entity_name).first()
        if entity is None:
            report["missing_operating_entities"] += 1
            continue
        for code, name in branches:
            branch, created = Branch.objects.get_or_create(
                organization=organization,
                code=code,
                defaults={"name": name, "operating_entity": entity},
            )
            if created:
                report["created"] += 1
                continue
            updates = []
            if branch.name != name:
                branch.name = name
                updates.append("name")
            if branch.operating_entity_id != entity.id:
                branch.operating_entity = entity
                updates.append("operating_entity")
            if updates:
                report["updated"] += 1
                if not dry_run:
                    branch.save(update_fields=updates + ["updated_at"])
            else:
                report["existing"] += 1
    for code, name in DEPARTMENTS:
        department, created = Department.objects.get_or_create(
            organization=organization,
            code=code,
            defaults={"name": name},
        )
        if created:
            report["created"] += 1
        elif department.name != name:
            report["updated"] += 1
            department.name = name
            if not dry_run:
                department.save(update_fields=["name", "updated_at"])
        else:
            report["existing"] += 1
    for branch in Branch.objects.filter(organization=organization, is_active=True).exclude(code__in=canonical_codes):
        if branch_dependency_count(branch):
            report["blocked"] += 1
            continue
        report["deactivated"] += 1
        if not dry_run:
            branch.is_active = False
            branch.save(update_fields=["is_active", "updated_at"])
    return report


def branch_dependency_count(branch):
    total = 0
    for model in apps.get_models():
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey) and field.remote_field.model is Branch:
                total += model.objects.filter(**{field.name: branch}).count()
    return total
