"""Plan, and only when explicitly asked apply, Rate Matrix tariff manifests (Pilot Gate B3H)."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.rate_matrix_loader import (
    TariffApplyError,
    apply_tariffs,
    plan_tariffs,
)


class Command(BaseCommand):
    help = (
        "Plan the insert of RateSheet, RateLine, RateApplicability and RateTier rows from one or more strict "
        "JSON manifests. Dry run by default: nothing is written without --apply. Several manifests are "
        "checked together, so tariffs that would be ambiguous across files are refused."
    )

    def add_arguments(self, parser):
        parser.add_argument("manifests", nargs="+", help="Path(s) to the JSON tariff manifest(s).")
        parser.add_argument("--format", choices=("text", "json"), default="text", help="Report format (default: text).")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the planned rows atomically. Requires --operator and --reviewed-sha256.",
        )
        parser.add_argument("--operator", help="Username of the active account applying the manifests.")
        parser.add_argument(
            "--reviewed-sha256",
            help=(
                "The 'Reviewed sha256' printed by the dry run that was reviewed and approved. For one "
                "manifest this is its own sha256 (of its text with newlines normalised, as the dry run "
                "prints it); for several it is the combined digest of all of them."
            ),
        )

    def handle(self, *args, **options):
        entries = []
        for name in options["manifests"]:
            path = Path(name)
            if not path.is_file():
                raise CommandError(f"Manifest file not found: {path}")
            try:
                entries.append((path.name, path.read_text(encoding="utf-8")))
            except UnicodeDecodeError as exc:
                raise CommandError(f"Manifest {path} is not valid UTF-8: {exc}") from exc

        if not options["apply"]:
            if options["operator"] or options["reviewed_sha256"]:
                raise CommandError("--operator and --reviewed-sha256 are only valid with --apply.")
            plan = plan_tariffs(entries)
        else:
            if not options["operator"] or not options["reviewed_sha256"]:
                raise CommandError("--apply requires --operator and --reviewed-sha256. Nothing was written.")
            operator = get_user_model().objects.filter(username=options["operator"], is_active=True).first()
            if operator is None:
                raise CommandError(f"No active user '{options['operator']}'. Nothing was written.")
            try:
                plan = apply_tariffs(entries, operator=operator, reviewed_sha256=options["reviewed_sha256"])
            except TariffApplyError as exc:
                raise CommandError(str(exc)) from exc

        self.stdout.write(plan.render_json() if options["format"] == "json" else plan.render_text())
        if not plan.ready:
            raise CommandError("Tariff plan is NOT READY. Nothing was written.")
