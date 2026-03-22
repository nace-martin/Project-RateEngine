from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand

from pricing_v4.engine.export_engine import ExportPricingEngine
from pricing_v4.models import ExportSellRate


class Command(BaseCommand):
    help = (
        "Ensure export D2A rate cards exist for the given year; "
        "seed missing corridors automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Target year to validate/seed (default: current year).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be seeded without writing changes.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if rates appear to exist.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        dry_run = options["dry_run"]
        force = options["force"]

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        fcy_start = date(year, 1, 2)

        self.stdout.write("=" * 72)
        self.stdout.write(f"Export D2A rate rollover check for {year}")
        self.stdout.write("=" * 72)

        required_ids = ExportPricingEngine.get_product_codes(
            is_dg=False,
            service_scope="D2A",
        )

        corridors = [
            {"origin": "POM", "dest": "BNE", "seed_cmd": "seed_export_pom_bne"},
            {"origin": "POM", "dest": "SYD", "seed_cmd": "seed_export_pom_syd"},
        ]

        for corridor in corridors:
            origin = corridor["origin"]
            dest = corridor["dest"]
            missing = self._missing_pgk_sell_rates(
                origin,
                dest,
                required_ids,
                year_start,
                year_end,
            )
            if force or missing:
                self._seed_corridor(
                    corridor["seed_cmd"],
                    year,
                    dry_run,
                    origin,
                    dest,
                    missing,
                )
            else:
                self.stdout.write(f"OK: {origin}->{dest} PGK sell rates present.")

        fcy_missing = self._missing_fcy_sell_rates(year_end, fcy_start)
        if force or fcy_missing:
            self._seed_fcy(year, dry_run, fcy_missing)
        else:
            self.stdout.write("OK: FCY export sell rates present.")

        self.stdout.write("=" * 72)
        self.stdout.write("Rollover check complete.")

    def _missing_pgk_sell_rates(self, origin, dest, required_ids, year_start, year_end):
        missing = []
        for pc_id in required_ids:
            exists = ExportSellRate.objects.filter(
                product_code_id=pc_id,
                origin_airport=origin,
                destination_airport=dest,
                currency="PGK",
                valid_from__lte=year_start,
                valid_until__gte=year_end,
            ).exists()
            if not exists:
                missing.append(pc_id)
        return missing

    def _missing_fcy_sell_rates(self, year_end, fcy_start):
        # Export Prepaid rates are FCY (AUD/USD) with valid_from on Jan 2
        fcy_dest_currency = {
            "BNE": "AUD",
            "CNS": "AUD",
            "SYD": "AUD",
            "HKG": "USD",
            "MNL": "USD",
            "HIR": "USD",
            "SIN": "USD",
            "VLI": "USD",
            "NAN": "USD",
        }

        missing = []
        for dest, currency in fcy_dest_currency.items():
            exists = ExportSellRate.objects.filter(
                product_code_id=1001,  # EXP-FRT-AIR
                origin_airport="POM",
                destination_airport=dest,
                currency=currency,
                valid_from__lte=fcy_start,
                valid_until__gte=year_end,
            ).exists()
            if not exists:
                missing.append(dest)
        return missing

    def _seed_corridor(self, seed_cmd, year, dry_run, origin, dest, missing):
        missing_display = ", ".join(str(x) for x in missing) if missing else "unknown"
        if dry_run:
            self.stdout.write(
                f"DRY RUN: would seed {origin}->{dest} via {seed_cmd} "
                f"(missing: {missing_display})"
            )
            return
        self.stdout.write(
            f"Seeding {origin}->{dest} via {seed_cmd} (missing: {missing_display})"
        )
        call_command(seed_cmd, year=year)

    def _seed_fcy(self, year, dry_run, missing):
        missing_display = ", ".join(missing) if missing else "unknown"
        if dry_run:
            self.stdout.write(
                f"DRY RUN: would seed FCY export rates (missing: {missing_display})"
            )
            return
        self.stdout.write(
            f"Seeding FCY export rates for {year} (missing: {missing_display})"
        )
        call_command("seed_export_sell_fcy", year=year)
