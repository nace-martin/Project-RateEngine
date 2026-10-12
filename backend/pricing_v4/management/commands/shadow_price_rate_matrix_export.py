"""Read-only export shadow pricing of Rate Matrix tariffs (Pilot Gate B3M-C)."""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.rate_matrix_export_shadow import (
    DEFAULT_CURRENCIES,
    DEFAULT_LANES,
    DEFAULT_SCOPES,
    DEFAULT_WEIGHTS,
    run_export_shadow,
)


class Command(BaseCommand):
    help = (
        "Price Pilot export scenarios (POM to BNE / SYD) twice with the production export engine: once from "
        "legacy PGK rate rows and once with Rate Matrix PGK tariffs, then compare line by line and total by "
        "total. AUD is the locked conversion of explicit PGK SELL (TT BUY, then export CAF). Read only: no "
        "row is written, no quote is affected, and no rate, FX, CAF or margin value is invented."
    )

    def add_arguments(self, parser):
        parser.add_argument("--lane", action="append", help="Origin-destination, e.g. POM-BNE. Repeatable.")
        parser.add_argument("--date", help="Quote date YYYY-MM-DD (default: today).")
        parser.add_argument("--weights", help="Comma-separated chargeable weights in kg.")
        parser.add_argument("--scopes", help="Comma-separated service scopes (A2A,D2A).")
        parser.add_argument("--currencies", help="Comma-separated quote currencies (PGK,AUD).")
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
                    raise CommandError(f"--lane must look like POM-BNE, got '{value}'.")
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
        scopes = tuple(p.strip().upper() for p in options["scopes"].split(",")) if options["scopes"] else DEFAULT_SCOPES
        for scope in scopes:
            if scope not in ("A2A", "D2A"):
                raise CommandError(f"--scopes must be A2A and/or D2A, got '{scope}'.")
        currencies = (
            tuple(p.strip().upper() for p in options["currencies"].split(",")) if options["currencies"]
            else DEFAULT_CURRENCIES
        )
        for currency in currencies:
            if currency not in ("PGK", "AUD"):
                raise CommandError(f"--currencies must be PGK and/or AUD, got '{currency}'.")

        report = run_export_shadow(
            quote_date=quote_date, lanes=lanes, weights=weights, scopes=scopes, currencies=currencies,
        )
        self.stdout.write(
            report.render_json() if options["format"] == "json"
            else report.render_text(show_matches=options["show_matches"])
        )
        if options["fail_on_unexplained"] and report.unexplained:
            raise CommandError("Unexplained differences exist.")
