import json

from django.core.management.base import BaseCommand

from quotes.services.air_freight_pilot_seed_plan import (
    apply_air_freight_pilot_seed_plan,
    build_air_freight_pilot_seed_plan,
    render_air_freight_pilot_seed_plan_text,
)


class Command(BaseCommand):
    help = "Air Freight pilot seed plan. Dry-run by default; --apply creates approved records."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["json", "text"], default="json")
        parser.add_argument("--apply", action="store_true", help="Create approved missing ProductCodes and ChargeAliases.")

    def handle(self, *args, **options):
        plan = apply_air_freight_pilot_seed_plan() if options["apply"] else build_air_freight_pilot_seed_plan()
        if options["format"] == "text":
            self.stdout.write(render_air_freight_pilot_seed_plan_text(plan), ending="")
            return
        self.stdout.write(json.dumps(plan, default=str, indent=2, sort_keys=True))
