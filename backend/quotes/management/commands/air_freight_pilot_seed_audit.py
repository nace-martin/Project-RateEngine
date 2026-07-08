import json

from django.core.management.base import BaseCommand

from quotes.services.air_freight_pilot_seed_audit import (
    build_air_freight_pilot_seed_audit,
    render_air_freight_pilot_seed_audit_text,
)


class Command(BaseCommand):
    help = "Read-only Air Freight pilot reference-data readiness audit."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["json", "text"], default="json")

    def handle(self, *args, **options):
        audit = build_air_freight_pilot_seed_audit()
        if options["format"] == "text":
            self.stdout.write(render_air_freight_pilot_seed_audit_text(audit), ending="")
            return
        self.stdout.write(json.dumps(audit, default=str, indent=2, sort_keys=True))
