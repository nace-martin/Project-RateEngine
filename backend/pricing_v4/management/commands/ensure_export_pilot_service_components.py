"""Plan, and only when explicitly asked create, the Pilot export ServiceComponent twins (Pilot Gate B3M-E)."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.export_pilot_components import (
    ExportComponentError,
    apply_export_components,
    plan_export_components,
)


class Command(BaseCommand):
    help = (
        "Plan the twelve same-code ServiceComponent twins the Rate Matrix export path requires. Dry run by "
        "default: nothing is written without --apply. Stored rows are never updated, a conflict writes "
        "nothing, and re-running is a no-op."
    )

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--apply", action="store_true", help="Create the missing twins atomically.")
        parser.add_argument("--operator", help="Username of the active account applying the set.")
        parser.add_argument("--reviewed-sha256", help="Combined sha256 printed by the reviewed dry run.")

    def handle(self, *args, **options):
        if not options["apply"]:
            if options["operator"] or options["reviewed_sha256"]:
                raise CommandError("--operator and --reviewed-sha256 are only valid with --apply.")
            plan = plan_export_components()
        else:
            if not options["operator"] or not options["reviewed_sha256"]:
                raise CommandError("--apply requires --operator and --reviewed-sha256. Nothing was written.")
            operator = get_user_model().objects.filter(username=options["operator"], is_active=True).first()
            if operator is None:
                raise CommandError(f"No active user '{options['operator']}'. Nothing was written.")
            try:
                plan = apply_export_components(operator=operator, reviewed_sha256=options["reviewed_sha256"])
            except ExportComponentError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(plan.as_dict(), indent=2, sort_keys=True) if options["format"] == "json" else plan.render_text()
        )
        if not plan.ready:
            raise CommandError("ServiceComponent twin plan is NOT READY. Nothing was written.")
