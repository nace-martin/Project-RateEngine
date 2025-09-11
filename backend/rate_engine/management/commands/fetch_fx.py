from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError

import logging
import os
from django.utils.timezone import now
from rate_engine.fx import EnvProvider, compute_tt_buy_sell, upsert_rate, d
from rate_engine.fx_providers import load as load_provider
from rate_engine.models import CurrencyRates as CurrencyRate


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
        parser.add_argument("--provider", type=str, default="bsp_html", help="FX provider to use (bsp_html|bsp|bank_bsp|env)")

    def handle(self, *args, **options):
        pairs_arg = options.get("pairs")
        if not pairs_arg:
            raise CommandError("--pairs is required (e.g., USD:PGK,PGK:USD)")
        pairs = parse_pairs(pairs_arg)

        spread_bps: int = options["spread_bps"]
        caf_pct = Decimal(options["caf_pct"])

        provider_name: str = (options["provider"] or "bsp_html").strip().lower()

        FX_STALE_HOURS = float(os.environ.get("FX_STALE_HOURS", 24))
        FX_ANOM_PCT = float(os.environ.get("FX_ANOMALY_PCT", 0.05))

        def latest_prev(base: str, quote: str):
            prev_buy = (CurrencyRate.objects
                        .filter(base_ccy=base, quote_ccy=quote, rate_type='BUY')
                        .order_by('-as_of_ts').first())
            prev_sell = (CurrencyRate.objects
                         .filter(base_ccy=base, quote_ccy=quote, rate_type='SELL')
                         .order_by('-as_of_ts').first())
            latest = None
            if prev_buy and prev_sell:
                latest = prev_buy if prev_buy.as_of_ts >= prev_sell.as_of_ts else prev_sell
            else:
                latest = prev_buy or prev_sell
            return latest, prev_buy, prev_sell

        def maybe_warn_stale(base: str, quote: str, latest_row):
            if not latest_row:
                return None
            age_hours = (now() - latest_row.as_of_ts).total_seconds() / 3600.0
            if age_hours > FX_STALE_HOURS:
                logging.warning("FX staleness: %s->%s latest %.1fh old", base, quote, age_hours)
            return age_hours

        def maybe_warn_anomaly(base: str, quote: str, rate_type: str, prev_rate, new_rate):
            try:
                if prev_rate and d(prev_rate) > 0:
                    pct = float(abs(d(new_rate) - d(prev_rate)) / d(prev_rate))
                    if pct > FX_ANOM_PCT:
                        logging.warning("FX anomaly: %s->%s %s changed by %.2f%% (old=%s new=%s)",
                                        base, quote, rate_type, pct*100.0, prev_rate, new_rate)
            except Exception:
                pass

        if provider_name in {"bsp_html", "bsp", "bank_bsp"}:
            provider = load_provider(provider_name)
            try:
                rows = provider.fetch([f"{b}:{q}" for (b, q) in pairs])
            except Exception as e:
                logging.warning("BSP provider failed, falling back to ENV: %s", e)
                provider_name = "env"
                rows = []

            if provider_name != "env":
                for (base, quote) in pairs:
                    latest, prev_buy, prev_sell = latest_prev(base, quote)
                    maybe_warn_stale(base, quote, latest)
                for r in rows:
                    prev_row = (CurrencyRate.objects.filter(base_ccy=r.base_ccy, quote_ccy=r.quote_ccy, rate_type=r.rate_type)
                                .order_by('-as_of_ts').first())
                    prev_val = prev_row.rate if prev_row else None
                    maybe_warn_anomaly(r.base_ccy, r.quote_ccy, r.rate_type, prev_val, r.rate)
                    upsert_rate(r.as_of_ts, r.base_ccy, r.quote_ccy, r.rate, r.rate_type, r.source)
                    self.stdout.write(self.style.SUCCESS(
                        f"Saved {r.base_ccy}->{r.quote_ccy} {r.rate_type} {r.rate} @ {r.as_of_ts.isoformat()} [{r.source}]"
                    ))

        if provider_name == "env":
            env = EnvProvider()
            for (base, quote) in pairs:
                latest, prev_buy, prev_sell = latest_prev(base, quote)
                maybe_warn_stale(base, quote, latest)
                mr = env.get_mid_rate(base, quote)
                buy, sell = compute_tt_buy_sell(mr.rate, spread_bps, caf_pct)
                maybe_warn_anomaly(base, quote, 'BUY', prev_buy.rate if prev_buy else None, buy)
                maybe_warn_anomaly(base, quote, 'SELL', prev_sell.rate if prev_sell else None, sell)
                upsert_rate(mr.as_of, base, quote, buy, 'BUY', 'ENV')
                upsert_rate(mr.as_of, base, quote, sell, 'SELL', 'ENV')
                self.stdout.write(self.style.SUCCESS(
                    f"Saved {base}->{quote} BUY {buy} / SELL {sell} @ {mr.as_of.isoformat()} [ENV]"
                ))
