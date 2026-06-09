import json

from django.core.management.base import BaseCommand

from accounts.rbac_seed import seed_rbac_foundation


class Command(BaseCommand):
    help = "Seed schema-only RBAC foundation data and backfill unambiguous user memberships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Print the seed summary as JSON.",
        )

    def handle(self, *args, **options):
        summary = seed_rbac_foundation()
        payload = summary.as_dict()
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return

        self.stdout.write(self.style.SUCCESS("RBAC foundation seed complete."))
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
