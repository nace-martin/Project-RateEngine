from django.core.management.base import BaseCommand, CommandError

from parties.models import Branch, OperatingEntity, Organization


ORGANIZATION = "Express Freight Management"
BRANCH_MAPPING = {
    "EFM PNG": ("Port Moresby", "Lae"),
    "EFM Australia": ("Brisbane",),
    "EFM Fiji": ("Suva",),
    "EFM Solomon Islands": ("Honiara",),
}


class Command(BaseCommand):
    help = "Idempotently link canonical Branch records to OperatingEntity records."

    def handle(self, *args, **options):
        organization = Organization.objects.filter(name=ORGANIZATION).first()
        if not organization:
            raise CommandError(f"Missing organization: {ORGANIZATION}")

        linked = existing = missing = 0
        for entity_name, branch_names in BRANCH_MAPPING.items():
            entity = OperatingEntity.objects.filter(organization=organization, name=entity_name).first()
            if not entity:
                raise CommandError(f"Missing operating entity: {entity_name}")
            for branch_name in branch_names:
                branch = Branch.objects.filter(organization=organization, name=branch_name).first()
                if not branch:
                    missing += 1
                    self.stdout.write(f"MISSING: {branch_name}")
                elif branch.operating_entity_id == entity.id:
                    existing += 1
                else:
                    branch.operating_entity = entity
                    branch.save(update_fields=["operating_entity", "updated_at"])
                    linked += 1
        self.stdout.write(f"Branch operating-entity link complete: linked={linked}, existing={existing}, missing={missing}")
