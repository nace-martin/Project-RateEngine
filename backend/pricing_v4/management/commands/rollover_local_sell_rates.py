from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import LocalSellRate


Key = Tuple[int, str, str, str, str]  # product_code_id, location, direction, payment_term, currency


@dataclass
class PlannedRollover:
    source_id: int
    key: Key
    source_valid_from: date
    source_valid_until: date


class Command(BaseCommand):
    help = (
        "Roll forward missing LocalSellRate rows into a target year for EXPORT/IMPORT locals. "
        "Safe and idempotent: only creates rows when no overlapping target-year row exists for the same key."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Target year to activate (default: current year).",
        )
        parser.add_argument(
            "--directions",
            nargs="+",
            choices=["EXPORT", "IMPORT"],
            default=["EXPORT", "IMPORT"],
            help="Directions to process (default: EXPORT IMPORT).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview planned rows without writing to DB.",
        )

    def handle(self, *args, **options):
        year: int = options["year"]
        directions: List[str] = options["directions"]
        dry_run: bool = options["dry_run"]

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        self.stdout.write("=" * 72)
        self.stdout.write(f"LocalSellRate rollover check for {year} ({', '.join(directions)})")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no changes will be committed"))
        self.stdout.write("=" * 72)

        latest_history_by_key = self._latest_historical_rows(directions, year_start)
        planned = self._build_plan(latest_history_by_key, year_start, year_end)

        if not planned:
            self.stdout.write(self.style.SUCCESS("No missing local sell rows detected for target year."))
            return

        self.stdout.write(f"Planned rollovers: {len(planned)}")
        preview_limit = 20
        for item in planned[:preview_limit]:
            product_code_id, location, direction, payment_term, currency = item.key
            self.stdout.write(
                f"  - PC {product_code_id} @ {location} [{direction}/{payment_term}/{currency}] "
                f"from source #{item.source_id} ({item.source_valid_from}..{item.source_valid_until}) "
                f"-> {year_start}..{year_end}"
            )
        if len(planned) > preview_limit:
            self.stdout.write(f"  ... and {len(planned) - preview_limit} more")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run complete."))
            return

        created = self._apply_plan(planned, year_start, year_end)
        self.stdout.write(self.style.SUCCESS(f"Created {created} LocalSellRate rows."))

    def _latest_historical_rows(
        self,
        directions: List[str],
        year_start: date,
    ) -> Dict[Key, LocalSellRate]:
        """
        Pick the latest historical row per commercial key (before target year).
        """
        rows = (
            LocalSellRate.objects.filter(
                direction__in=directions,
                valid_from__lt=year_start,
            )
            .select_related("product_code", "percent_of_product_code")
            .order_by(
                "product_code_id",
                "location",
                "direction",
                "payment_term",
                "currency",
                "-valid_until",
                "-valid_from",
                "-id",
            )
        )

        latest: Dict[Key, LocalSellRate] = {}
        for row in rows:
            key: Key = (
                row.product_code_id,
                row.location,
                row.direction,
                row.payment_term,
                row.currency,
            )
            if key not in latest:
                latest[key] = row
        return latest

    def _build_plan(
        self,
        latest_history_by_key: Dict[Key, LocalSellRate],
        year_start: date,
        year_end: date,
    ) -> List[PlannedRollover]:
        planned: List[PlannedRollover] = []
        for key, source in latest_history_by_key.items():
            product_code_id, location, direction, payment_term, currency = key

            has_target_overlap = LocalSellRate.objects.filter(
                product_code_id=product_code_id,
                location=location,
                direction=direction,
                payment_term=payment_term,
                currency=currency,
                valid_from__lte=year_end,
                valid_until__gte=year_start,
            ).exists()
            if has_target_overlap:
                continue

            planned.append(
                PlannedRollover(
                    source_id=source.id,
                    key=key,
                    source_valid_from=source.valid_from,
                    source_valid_until=source.valid_until,
                )
            )
        return planned

    def _apply_plan(self, planned: List[PlannedRollover], year_start: date, year_end: date) -> int:
        created = 0
        with transaction.atomic():
            for item in planned:
                source = LocalSellRate.objects.select_related("percent_of_product_code").get(id=item.source_id)
                product_code_id, location, direction, payment_term, currency = item.key

                # Re-check overlap to stay safe if data changed since planning.
                if LocalSellRate.objects.filter(
                    product_code_id=product_code_id,
                    location=location,
                    direction=direction,
                    payment_term=payment_term,
                    currency=currency,
                    valid_from__lte=year_end,
                    valid_until__gte=year_start,
                ).exists():
                    continue

                LocalSellRate.objects.create(
                    product_code=source.product_code,
                    location=location,
                    direction=direction,
                    payment_term=payment_term,
                    currency=currency,
                    rate_type=source.rate_type,
                    amount=source.amount,
                    is_additive=source.is_additive,
                    additive_flat_amount=source.additive_flat_amount,
                    min_charge=source.min_charge,
                    max_charge=source.max_charge,
                    weight_breaks=deepcopy(source.weight_breaks),
                    percent_of_product_code=source.percent_of_product_code,
                    valid_from=year_start,
                    valid_until=year_end,
                )
                created += 1
        return created
