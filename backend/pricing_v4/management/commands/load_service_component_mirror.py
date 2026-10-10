"""Plan, and only when explicitly asked create, one same-code ServiceComponent (Pilot Gate B3H)."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.service_component_mirror import (
    ComponentApplyError,
    apply_component_text,
    plan_component_text,
)


class Command(BaseCommand):
    help = (
        "Plan the creation of exactly one ServiceComponent that shares its code with an existing ProductCode "
        "and CommercialProductCode, from a strict JSON manifest. Dry run by default: nothing is written "
        "without --apply. Stored rows are never updated and sync_v4_components is not involved."
    )

    def add_arguments(self, parser):
        parser.add_argument("manifest", help="Path to the JSON ServiceComponent manifest.")
        parser.add_argument("--format", choices=("text", "json"), default="text", help="Report format (default: text).")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the planned row atomically. Requires --operator and --reviewed-sha256.",
        )
        parser.add_argument("--operator", help="Username of the active account applying the manifest.")
        parser.add_argument(
            "--reviewed-sha256",
            help="Manifest sha256 printed by the dry run that was reviewed and approved.",
        )

    def handle(self, *args, **options):
        path = Path(options["manifest"])
        if not path.is_file():
            raise CommandError(f"Manifest file not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CommandError(f"Manifest is not valid UTF-8: {exc}") from exc

        if not options["apply"]:
            if options["operator"] or options["reviewed_sha256"]:
                raise CommandError("--operator and --reviewed-sha256 are only valid with --apply.")
            plan = plan_component_text(text)
        else:
            if not options["operator"] or not options["reviewed_sha256"]:
                raise CommandError("--apply requires --operator and --reviewed-sha256. Nothing was written.")
            operator = get_user_model().objects.filter(username=options["operator"], is_active=True).first()
            if operator is None:
                raise CommandError(f"No active user '{options['operator']}'. Nothing was written.")
            try:
                plan = apply_component_text(text, operator=operator, reviewed_sha256=options["reviewed_sha256"])
            except ComponentApplyError as exc:
                raise CommandError(str(exc)) from exc

        self.stdout.write(plan.render_json() if options["format"] == "json" else plan.render_text())
        if not plan.ready:
            raise CommandError("ServiceComponent plan is NOT READY. Nothing was written.")
