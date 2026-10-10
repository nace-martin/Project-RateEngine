"""Read-only Stage-1 shadow comparison of Rate Matrix tariffs against legacy rates (Pilot Gate B3J)."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.rate_matrix_shadow import (
    DEFAULT_LANES,
    DEFAULT_WEIGHTS,
    load_registry,
    run_shadow,
)


class Command(BaseCommand):
    help = (
        "Compare Rate Matrix native tariff facts with legacy ImportCOGS / LocalSellRate facts. Read only: no "
        "row is written, no FX, CAF, margin, GST or quote total is computed, and no quote is affected."
    )

    def add_arguments(self, parser):
        parser.add_argument("--lane", action="append", help="Origin-destination, e.g. BNE-POM. Repeatable.")
        parser.add_argument("--date", help="Quote date YYYY-MM-DD (default: today).")
        parser.add_argument("--weights", help="Comma-separated chargeable weights in kg.")
        parser.add_argument("--explained", help="Path to an explained-differences registry JSON.")
        parser.add_argument("--legacy-agent-code", help="Restrict legacy ImportCOGS to this Agent code.")
        parser.add_argument("--show-matches", action="store_true", help="Also list MATCH records in text output.")
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument(
            "--fail-on-unexplained", action="store_true",
            help="Exit non-zero when any UNEXPLAINED_DIFFERENCE or a stale registry entry exists.",
        )

    def handle(self, *args, **options):
        lanes = DEFAULT_LANES
        if options["lane"]:
            lanes = []
            for value in options["lane"]:
                origin, _, destination = value.partition("-")
                if len(origin) != 3 or len(destination) != 3:
                    raise CommandError(f"--lane must look like BNE-POM, got '{value}'.")
                lanes.append((origin.upper(), destination.upper()))
        try:
            quote_date = date.fromisoformat(options["date"]) if options["date"] else date.today()  # noqa: DTZ011 - a calendar date, not a timestamp
        except ValueError as exc:
            raise CommandError(f"--date must be YYYY-MM-DD: {exc}") from exc
        weights = DEFAULT_WEIGHTS
        if options["weights"]:
            try:
                weights = tuple(Decimal(part.strip()) for part in options["weights"].split(",") if part.strip())
            except InvalidOperation as exc:
                raise CommandError("--weights must be comma-separated numbers.") from exc
        registry, registry_errors = [], []
        if options["explained"]:
            path = Path(options["explained"])
            if not path.is_file():
                raise CommandError(f"Registry file not found: {path}")
            registry, registry_errors = load_registry(path.read_text(encoding="utf-8"))

        report = run_shadow(
            quote_date=quote_date, lanes=lanes, weights=weights, registry=registry,
            registry_errors=registry_errors, legacy_agent_code=options["legacy_agent_code"],
        )
        self.stdout.write(
            report.render_json() if options["format"] == "json"
            else report.render_text(show_matches=options["show_matches"])
        )
        if options["fail_on_unexplained"] and (
            report.unexplained or report.stale_registry_entries or report.registry_errors
        ):
            raise CommandError("Unexplained differences, stale registry entries, or registry errors exist.")
