from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError

import logging
import os
from django.utils.timezone import now
from core.fx import upsert_rate, d
from core.fx_providers import load as load_provider


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
    help = "Fetch FX rates from BSP and persist to FxSnapshot."

    def add_arguments(self, parser):
        parser.add_argument("--pairs", type=str, help="Comma-separated pairs BASE:QUOTE, e.g., USD:PGK,PGK:USD")
        parser.add_argument("--provider", type=str, default="bsp_html", help="FX provider to use (bsp_html|bsp|bank_bsp)")

    def handle(self, *args, **options):
        pairs_arg = options.get("pairs")
        if not pairs_arg:
            raise CommandError("--pairs is required (e.g., USD:PGK,PGK:USD)")
        pairs = parse_pairs(pairs_arg)

        provider_name: str = (options["provider"] or "bsp_html").strip().lower()

        if provider_name not in {"bsp_html", "bsp", "bank_bsp"}:
            raise CommandError(f"Unknown provider: {provider_name}")

        provider = load_provider(provider_name)
        
        self.stdout.write(f"Fetching FX rates from {provider_name}...")
        
        try:
            rows = provider.fetch([f"{b}:{q}" for (b, q) in pairs])
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"BSP provider failed: {e}"))
            raise CommandError(f"Failed to fetch rates: {e}")

        if not rows:
            self.stderr.write(self.style.WARNING("No rates returned from BSP"))
            return

        for r in rows:
            upsert_rate(r.as_of_ts, r.base_ccy, r.quote_ccy, r.rate, r.rate_type, r.source)
            self.stdout.write(self.style.SUCCESS(
                f"Saved {r.base_ccy}->{r.quote_ccy} {r.rate_type} {r.rate} @ {r.as_of_ts.isoformat()} [{r.source}]"
            ))

        self.stdout.write(self.style.SUCCESS(f"Successfully saved {len(rows)} FX rates"))
