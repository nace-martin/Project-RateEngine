from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.fx import FxUnavailableError, upsert_market_rate
from core.fx_providers import load as load_provider

logger = logging.getLogger(__name__)


def parse_pairs(arg: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for part in (arg or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise CommandError(
                f"Invalid pair '{part}'. Use BASE:QUOTE, e.g., AUD:PGK"
            )
        base, quote = part.split(":", 1)
        pairs.append((base.strip().upper(), quote.strip().upper()))
    return pairs


class Command(BaseCommand):
    help = "Fetch FX rates from BSP and persist canonical FxMarketRate facts plus historical FxSnapshot evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pairs",
            type=str,
            help="Comma-separated pairs BASE:QUOTE, e.g., AUD:PGK,USD:PGK",
        )
        parser.add_argument(
            "--provider",
            type=str,
            default="bsp_html",
            help="FX provider to use (bsp_html|bsp|bank_bsp)",
        )

    def handle(self, *args, **options):
        pairs_arg = options.get("pairs")
        if not pairs_arg:
            raise CommandError("--pairs is required (e.g., AUD:PGK,USD:PGK)")
        pairs = parse_pairs(pairs_arg)

        provider_name = (options["provider"] or "bsp_html").strip().lower()
        if provider_name not in {"bsp_html", "bsp", "bank_bsp"}:
            raise CommandError(f"Unknown provider: {provider_name}")

        provider = load_provider(provider_name)
        self.stdout.write(f"Fetching FX rates from {provider_name}...")

        try:
            rows = provider.fetch([f"{base}:{quote}" for base, quote in pairs])
        except Exception as exc:
            # Do not relabel historical data as fresh.  Existing FxMarketRate
            # facts remain available to the quote-date resolver; the refresh
            # itself fails closed and surfaces the provider failure.
            message = (
                f"FX refresh failed for provider {provider_name}: {exc}. "
                "No new market facts were written; existing historical facts were left unchanged."
            )
            logger.error(message)
            raise CommandError(message) from exc

        if not rows:
            raise CommandError(
                f"Provider {provider_name} returned no FX rows; no market facts were written."
            )

        grouped = defaultdict(dict)
        timestamps = {}
        for row in rows:
            base = str(row.base_ccy or "").strip().upper()
            quote = str(row.quote_ccy or "").strip().upper()
            source = str(row.source or provider_name).strip()
            day = row.as_of_ts.date()
            key = (base, quote, source, day)
            side = str(row.rate_type or "").strip().upper()
            if side not in {"BUY", "SELL"}:
                raise CommandError(
                    f"Provider returned unsupported rate type '{row.rate_type}' for {base}/{quote}."
                )
            grouped[key][side] = Decimal(str(row.rate))
            timestamps[key] = max(timestamps.get(key, row.as_of_ts), row.as_of_ts)

        incomplete = [
            f"{base}/{quote} [{source}] {day}"
            for (base, quote, source, day), sides in grouped.items()
            if "BUY" not in sides or "SELL" not in sides
        ]
        if incomplete:
            raise CommandError(
                "Provider returned incomplete BUY/SELL market facts for: "
                + ", ".join(incomplete)
            )

        saved = 0
        try:
            with transaction.atomic():
                for (base, quote, source, day), sides in grouped.items():
                    market_rate = upsert_market_rate(
                        as_of=timestamps[(base, quote, source, day)],
                        base_ccy=base,
                        quote_ccy=quote,
                        tt_buy=sides["BUY"],
                        tt_sell=sides["SELL"],
                        source=source,
                        update_snapshot=True,
                    )
                    saved += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Saved "
                            f"{market_rate.base_currency}/{market_rate.quote_currency} "
                            f"BUY {market_rate.tt_buy_rate} SELL {market_rate.tt_sell_rate} "
                            f"@ {market_rate.effective_date} [{market_rate.source}]"
                        )
                    )
        except FxUnavailableError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Successfully saved {saved} complete FX market facts")
        )
