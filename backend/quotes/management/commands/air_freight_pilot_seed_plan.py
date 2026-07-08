import json

from django.core.management.base import BaseCommand

from quotes.services.air_freight_pilot_seed_plan import (
    build_air_freight_pilot_seed_plan,
    render_air_freight_pilot_seed_plan_text,
)


class Command(BaseCommand):
    help = "Dry-run-only Air Freight pilot seed plan. This command performs no writes."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["json", "text"], default="json")

    def handle(self, *args, **options):
        plan = build_air_freight_pilot_seed_plan()
        if options["format"] == "text":
            self.stdout.write(render_air_freight_pilot_seed_plan_text(plan), ending="")
            return
        self.stdout.write(json.dumps(plan, default=str, indent=2, sort_keys=True))
