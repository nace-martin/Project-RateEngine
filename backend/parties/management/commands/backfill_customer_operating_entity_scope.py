from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from parties.models import Company, OperatingEntity, Organization


class Command(BaseCommand):
    help = "Backfill customer master organization and operating-entity scope. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True, help="Target organization name.")
        parser.add_argument("--operating-entity", required=True, help="Target operating entity name.")
        parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to dry-run.")

    def handle(self, *args, **options):
        organization = Organization.objects.filter(name=options["organization"]).first()
        if organization is None:
            raise CommandError(f"Organization not found: {options['organization']}")

        operating_entity = OperatingEntity.objects.filter(
            organization=organization,
            name=options["operating_entity"],
        ).first()
        if operating_entity is None:
            raise CommandError(
                f"Operating entity not found under {organization.name}: {options['operating_entity']}"
            )

        customers = Company.objects.filter(Q(is_customer=True) | Q(company_type="CUSTOMER"))
        candidates = customers.filter(Q(organization__isnull=True) | Q(operating_entity__isnull=True))
        candidate_count = candidates.count()
        sample_names = list(candidates.order_by("name").values_list("name", flat=True)[:10])
        before_missing = customers.filter(Q(organization__isnull=True) | Q(operating_entity__isnull=True)).count()

        if options["apply"]:
            with transaction.atomic():
                candidates.update(organization=organization, operating_entity=operating_entity)

        after_missing = customers.filter(Q(organization__isnull=True) | Q(operating_entity__isnull=True)).count()
        mode = "APPLIED" if options["apply"] else "DRY RUN"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Customer operating-entity scope backfill"))
        self.stdout.write(f"- Customers considered: {customers.count()}")
        self.stdout.write(f"- Customers needing scope before: {before_missing}")
        self.stdout.write(f"- Customers needing scope after: {after_missing}")
        self.stdout.write(f"- Customers eligible for update: {candidate_count}")
        self.stdout.write("- Sample affected customers:")
        for name in sample_names:
            self.stdout.write(f"  - {name}")
