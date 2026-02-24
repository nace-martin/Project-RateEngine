from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError

import logging
import os
from django.utils.timezone import now
from core.fx import upsert_rate, d, FxUnavailableError
from core.fx_providers import load as load_provider
from core.models import FxSnapshot

logger = logging.getLogger(__name__)

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
        
        rows = []
        try:
            rows = provider.fetch([f"{b}:{q}" for (b, q) in pairs])
        except Exception as e:
            msg = f"CRITICAL: BSP FX Scraper failed: {e}. Attempting fallback to Last Known Good rates."
            self.stderr.write(self.style.ERROR(msg))
            logger.error(msg)
            
            # --- FALLBACK MECHANISM: Last Known Good (LKG) ---
            last_good = FxSnapshot.objects.filter(source=provider_name).order_by('-as_of_timestamp').first()
            if not last_good:
                # Secondary fallback: any successful snapshot
                last_good = FxSnapshot.objects.exclude(rates={}).order_by('-as_of_timestamp').first()
            
            if last_good:
                self.stdout.write(self.style.WARNING(f"Falling back to rates from snapshot as of {last_good.as_of_timestamp}"))
                # Use LKG rates but update the timestamp to now to keep engine running
                # In a real scenario, you might want to flag these as 'STALE'
                rows = []
                from core.fx_providers import RateRow
                
                snapshot_rates = {
                    str(pair).upper(): values
                    for pair, values in (last_good.rates or {}).items()
                    if isinstance(values, dict)
                }
                missing_pairs: List[str] = []
                fallback_source = f"{last_good.source}_fallback"
                fallback_as_of = now()

                def _q4(value: Decimal) -> Decimal:
                    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

                for base, quote in pairs:
                    requested_key = f"{base}/{quote}".upper()
                    inverse_key = f"{quote}/{base}".upper()
                    values = snapshot_rates.get(requested_key)
                    pair_rows_before = len(rows)

                    if values:
                        if 'tt_buy' in values:
                            rows.append(RateRow(fallback_as_of, base, quote, d(values['tt_buy']), "BUY", fallback_source))
                        if 'tt_sell' in values:
                            rows.append(RateRow(fallback_as_of, base, quote, d(values['tt_sell']), "SELL", fallback_source))
                    else:
                        inverse_values = snapshot_rates.get(inverse_key)
                        if inverse_values:
                            # Reconstruct requested direction from inverse snapshot:
                            # BUY(base/quote) = 1 / SELL(quote/base)
                            # SELL(base/quote) = 1 / BUY(quote/base)
                            inv_sell = inverse_values.get('tt_sell')
                            inv_buy = inverse_values.get('tt_buy')
                            if inv_sell not in (None, "", "0", "0.0", "0.0000"):
                                rows.append(
                                    RateRow(
                                        fallback_as_of,
                                        base,
                                        quote,
                                        _q4(Decimal("1") / d(inv_sell)),
                                        "BUY",
                                        fallback_source,
                                    )
                                )
                            if inv_buy not in (None, "", "0", "0.0", "0.0000"):
                                rows.append(
                                    RateRow(
                                        fallback_as_of,
                                        base,
                                        quote,
                                        _q4(Decimal("1") / d(inv_buy)),
                                        "SELL",
                                        fallback_source,
                                    )
                                )

                    if len(rows) == pair_rows_before:
                        missing_pairs.append(requested_key)

                if missing_pairs:
                    error_msg = (
                        "FATAL: FX fallback snapshot does not contain all requested pairs. "
                        f"Missing: {', '.join(missing_pairs)}"
                    )
                    logger.error(error_msg)
                    raise FxUnavailableError(error_msg)
            else:
                # --- FAIL-CLOSED STATE ---
                error_msg = "FATAL: FX Scraping failed and no historical rates found in database. Quoting engine halted."
                logger.error(error_msg)
                raise FxUnavailableError(error_msg)

        if not rows:
            self.stderr.write(self.style.WARNING("No rates returned from BSP or Fallback"))
            return

        for r in rows:
            upsert_rate(r.as_of_ts, r.base_ccy, r.quote_ccy, r.rate, r.rate_type, r.source)
            self.stdout.write(self.style.SUCCESS(
                f"Saved {r.base_ccy}->{r.quote_ccy} {r.rate_type} {r.rate} @ {r.as_of_ts.isoformat()} [{r.source}]"
            ))

        self.stdout.write(self.style.SUCCESS(f"Successfully saved {len(rows)} FX rates"))
