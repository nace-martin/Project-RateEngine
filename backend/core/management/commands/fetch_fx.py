from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError

from django.db import transaction
from core.fx_market_models import FxMarketRate
from core.fx_providers import load as load_provider
from core.models import FxSnapshot

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
    help = "Fetch complete bank TT rates and persist FxMarketRate facts and snapshots."

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
        except Exception as exc:
            raise CommandError(f"FX fetch failed for {provider_name}: {exc}") from exc

        if not rows:
            raise CommandError("Provider returned no FX rates")

        market_facts = []
        canonical_facts = {}
        snapshot_rates = {}
        for base, quote in pairs:
            pair_rows = [row for row in rows if row.base_ccy == base and row.quote_ccy == quote]
            sides = {row.rate_type: row for row in pair_rows}
            if len(pair_rows) != 2 or set(sides) != {"BUY", "SELL"}:
                raise CommandError(f"Incomplete or duplicate TT BUY/SELL for {base}/{quote}")
            buy, sell = sides["BUY"], sides["SELL"]
            if not buy.effective_date or buy.source != sell.source or buy.effective_date != sell.effective_date:
                raise CommandError(f"Mismatched FX provenance for {base}/{quote}")
            if buy.rate <= 0 or sell.rate <= 0:
                raise CommandError(f"Nonpositive FX rate for {base}/{quote}")
            if base == 'PGK' and quote != 'PGK':
                fcy = quote
                tt_buy, tt_sell = Decimal(1) / sell.rate, Decimal(1) / buy.rate
            elif quote == 'PGK' and base != 'PGK':
                fcy = base
                tt_buy, tt_sell = buy.rate, sell.rate
            else:
                raise CommandError(f"Fetch requires a PGK pair: {base}/{quote}")
            tt_buy = tt_buy.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            tt_sell = tt_sell.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            if tt_sell < tt_buy:
                raise CommandError(f"TT SELL is below TT BUY for {fcy}/PGK")
            key = (fcy, buy.effective_date, buy.source)
            rates = (tt_buy, tt_sell)
            if key in canonical_facts and canonical_facts[key] != rates:
                raise CommandError(f"Conflicting canonical FX facts for {fcy}/PGK on {key[1]}")
            if key not in canonical_facts:
                market_facts.append((fcy, buy.effective_date, buy.source, tt_buy, tt_sell))
            canonical_facts[key] = rates
            snapshot_rates[fcy] = {'tt_buy': str(tt_buy), 'tt_sell': str(tt_sell)}

        with transaction.atomic():
            for fcy, effective_date, source, tt_buy, tt_sell in market_facts:
                FxMarketRate.objects.update_or_create(
                    base_currency=fcy, quote_currency='PGK',
                    effective_date=effective_date, source=source,
                    defaults={
                        'tt_buy_rate': tt_buy,
                        'tt_sell_rate': tt_sell,
                        'mid_rate': ((tt_buy + tt_sell) / 2).quantize(
                            Decimal('0.00000001'), rounding=ROUND_HALF_UP
                        ),
                    },
                )
            FxSnapshot.objects.create(
                as_of_timestamp=max(row.observed_at for row in rows),
                source=provider_name,
                rates=snapshot_rates,
                caf_percent=Decimal(0),
                fx_buffer_percent=Decimal(0),
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully saved {len(rows)} FX rates"))
