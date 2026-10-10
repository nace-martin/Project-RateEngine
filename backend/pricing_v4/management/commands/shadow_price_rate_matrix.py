"""Read-only Stage-2 commercial shadow pricing of Rate Matrix tariffs (Pilot Gate B3K)."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.rate_matrix_shadow import load_registry
from pricing_v4.services.rate_matrix_stage2_shadow import (
    DEFAULT_LANES,
    DEFAULT_SCOPES,
    DEFAULT_TERMS,
    DEFAULT_WEIGHTS,
    run_stage2,
)


class Command(BaseCommand):
    help = (
        "Price Pilot import scenarios twice with the production import engine: once from legacy rate rows and "
        "once with Rate Matrix tariffs, then compare line by line and total by total. Read only: no row is "
        "written, no quote is affected, and no CAF, margin, GST or FX value is invented. Policy and FX values "
        "read are legacy observed policy and are NOT approved for cutover."
    )

    def add_arguments(self, parser):
        parser.add_argument("--lane", action="append", help="Origin-destination, e.g. BNE-POM. Repeatable.")
        parser.add_argument("--date", help="Quote date YYYY-MM-DD (default: today).")
        parser.add_argument("--weights", help="Comma-separated chargeable weights in kg.")
        parser.add_argument("--terms", help="Comma-separated payment terms (COLLECT,PREPAID).")
        parser.add_argument("--scopes", help="Comma-separated service scopes (A2D,D2D,D2A,A2A).")
        parser.add_argument("--explained", help="Stage-1 explained-differences registry JSON (see shadow_compare_rate_matrix).")
        parser.add_argument(
            "--max-fx-age-days", type=int,
            help="Block a scenario whose FX rate is older than this many days. No default is assumed.",
        )
        parser.add_argument("--show-matches", action="store_true")
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--fail-on-unexplained", action="store_true")

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
            quote_date = date.fromisoformat(options["date"]) if options["date"] else date.today()  # noqa: DTZ011
        except ValueError as exc:
            raise CommandError(f"--date must be YYYY-MM-DD: {exc}") from exc
        weights = DEFAULT_WEIGHTS
        if options["weights"]:
            try:
                weights = tuple(Decimal(p.strip()) for p in options["weights"].split(",") if p.strip())
            except InvalidOperation as exc:
                raise CommandError("--weights must be comma-separated numbers.") from exc
        terms = tuple(p.strip().upper() for p in options["terms"].split(",")) if options["terms"] else DEFAULT_TERMS
        scopes = tuple(p.strip().upper() for p in options["scopes"].split(",")) if options["scopes"] else DEFAULT_SCOPES
        for term in terms:
            if term not in ("COLLECT", "PREPAID"):
                raise CommandError(f"--terms must be COLLECT and/or PREPAID, got '{term}'.")
        for scope in scopes:
            if scope not in ("A2A", "A2D", "D2A", "D2D"):
                raise CommandError(f"--scopes must be A2A, A2D, D2A and/or D2D, got '{scope}'.")
        registry = []
        if options["explained"]:
            path = Path(options["explained"])
            if not path.is_file():
                raise CommandError(f"Registry file not found: {path}")
            registry, errors = load_registry(path.read_text(encoding="utf-8"))
            if errors:
                raise CommandError("Registry errors: " + "; ".join(errors))

        report = run_stage2(
            quote_date=quote_date, lanes=lanes, weights=weights, terms=terms, scopes=scopes,
            stage1_registry=registry, max_fx_age_days=options["max_fx_age_days"],
        )
        self.stdout.write(
            report.render_json() if options["format"] == "json"
            else report.render_text(show_matches=options["show_matches"])
        )
        if options["fail_on_unexplained"] and report.unexplained:
            raise CommandError("Unexplained differences exist.")
