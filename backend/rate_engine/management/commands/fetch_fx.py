from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError

from rate_engine.fx import EnvProvider, refresh_fx


def parse_pairs(arg: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for part in (arg or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise CommandError(f"Invalid pair '{part}'. Use BASE:QUOTE, e.g., USD:PGK")
        b, q = part.split(":", 1)
        pairs.append((b.strip().upper(), q.strip().upper()))
    return pairs


class Command(BaseCommand):
    help = "Fetch FX mid rates and persist TT BUY/SELL rates using configured provider (ENV by default)."

    def add_arguments(self, parser):
        parser.add_argument("--pairs", type=str, help="Comma-separated pairs BASE:QUOTE, e.g., USD:PGK,PGK:USD")
        parser.add_argument("--spread-bps", type=int, default=100, help="Spread in basis points applied to mid")
        parser.add_argument("--caf-pct", type=str, default="0.065", help="CAF percentage, e.g., 0.065 for 6.5%")

    def handle(self, *args, **options):
        pairs_arg = options.get("pairs")
        if not pairs_arg:
            raise CommandError("--pairs is required (e.g., USD:PGK,PGK:USD)")
        pairs = parse_pairs(pairs_arg)

        spread_bps: int = options["spread_bps"]
        caf_pct = Decimal(options["caf_pct"])

        provider = EnvProvider()
        summary = refresh_fx(pairs, provider, spread_bps=spread_bps, caf_pct=caf_pct, source_label="ENV")
        for row in summary:
            self.stdout.write(self.style.SUCCESS(f"Saved {row['pair']} @ {row['as_of']} mid={row['mid']} buy={row['buy']} sell={row['sell']}"))

