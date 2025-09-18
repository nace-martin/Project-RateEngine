from __future__ import annotations

import logging
import os
from typing import List, Tuple

from django.utils.timezone import now

from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.fx import EnvProvider, compute_tt_buy_sell, upsert_rate
from core.fx_providers import load as load_fx_provider
from core.models import CurrencyRates as CurrencyRate
from pricing.services.utils import d


class FxRefreshView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        role = getattr(user, "role", "")
        if role not in ("manager", "finance"):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        pairs_arg = request.data.get("pairs")
        spread_bps = int(request.data.get("spread_bps", 100))
        caf_pct = d(request.data.get("caf_pct", "0.065"))

        if not pairs_arg:
            return Response(
                {"detail": "pairs is required, e.g., ['USD:PGK','PGK:USD']"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(pairs_arg, str):
            parts: List[str] = [p.strip() for p in pairs_arg.split(",") if p.strip()]
        else:
            parts = list(pairs_arg)
        pairs: List[Tuple[str, str]] = []
        for p in parts:
            if ":" not in p:
                return Response(
                    {"detail": f"Invalid pair '{p}'. Use BASE:QUOTE"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            b, q = p.split(":", 1)
            pairs.append((b.strip().upper(), q.strip().upper()))

        provider_name = (request.data.get("provider") or "bsp_html").strip().lower()
        FX_STALE_HOURS = float(os.environ.get("FX_STALE_HOURS", 24))
        FX_ANOM_PCT = float(os.environ.get("FX_ANOMALY_PCT", 0.05))

        def latest_prev_for_pair(base: str, quote: str):
            prev_buy = (
                CurrencyRate.objects.filter(base_ccy=base, quote_ccy=quote, rate_type="BUY")
                .order_by("-as_of_ts")
                .first()
            )
            prev_sell = (
                CurrencyRate.objects.filter(base_ccy=base, quote_ccy=quote, rate_type="SELL")
                .order_by("-as_of_ts")
                .first()
            )
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
                        logging.warning(
                            "FX anomaly: %s->%s %s changed by %.2f%% (old=%s new=%s)",
                            base,
                            quote,
                            rate_type,
                            pct * 100.0,
                            prev_rate,
                            new_rate,
                        )
            except Exception:
                pass

        summary = []

        if provider_name in {"bsp_html", "bsp", "bank_bsp"}:
            provider = load_fx_provider(provider_name)
            try:
                rows = provider.fetch([f"{b}:{q}" for (b, q) in pairs])
            except Exception as e:
                logging.warning("BSP provider failed, falling back to ENV: %s", e)
                provider_name = "env"
                provider = EnvProvider()
                rows = []  # will be populated in env branch below

            if provider_name != "env":
                for base, quote in pairs:
                    latest, prev_buy_row, prev_sell_row = latest_prev_for_pair(base, quote)
                    age_hours = maybe_warn_stale(base, quote, latest)
                for r in rows:
                    prev_row = (
                        CurrencyRate.objects.filter(
                            base_ccy=r.base_ccy,
                            quote_ccy=r.quote_ccy,
                            rate_type=r.rate_type,
                        )
                        .order_by("-as_of_ts")
                        .first()
                    )
                    prev_val = prev_row.rate if prev_row else None
                    maybe_warn_anomaly(r.base_ccy, r.quote_ccy, r.rate_type, prev_val, r.rate)
                    upsert_rate(r.as_of_ts, r.base_ccy, r.quote_ccy, r.rate, r.rate_type, r.source)
                    summary.append(
                        {
                            "pair": f"{r.base_ccy}->{r.quote_ccy}",
                            "as_of": r.as_of_ts.isoformat(),
                            "mid": None,
                            "buy": str(r.rate) if r.rate_type == "BUY" else None,
                            "sell": str(r.rate) if r.rate_type == "SELL" else None,
                            "source": r.source,
                        }
                    )

        if provider_name == "env":
            env = EnvProvider()
            for base, quote in pairs:
                latest, prev_buy_row, prev_sell_row = latest_prev_for_pair(base, quote)
                age_hours = maybe_warn_stale(base, quote, latest)
                try:
                    mr = env.get_mid_rate(base, quote)
                    buy, sell = compute_tt_buy_sell(mr.rate, spread_bps, caf_pct)
                except Exception as e:
                    return Response(
                        {"detail": f"ENV provider failed for {base}->{quote}: {e}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                maybe_warn_anomaly(base, quote, "BUY", prev_buy_row.rate if prev_buy_row else None, buy)
                maybe_warn_anomaly(base, quote, "SELL", prev_sell_row.rate if prev_sell_row else None, sell)
                upsert_rate(mr.as_of, base, quote, buy, "BUY", "ENV")
                upsert_rate(mr.as_of, base, quote, sell, "SELL", "ENV")
                summary.append(
                    {
                        "pair": f"{base}->{quote}",
                        "as_of": mr.as_of.isoformat(),
                        "mid": str(mr.rate),
                        "buy": str(buy),
                        "sell": str(sell),
                        "source": "ENV",
                        **({"fx_age_hours": round(age_hours, 1)} if age_hours is not None else {}),
                    }
                )

        return Response({"updated": summary}, status=status.HTTP_200_OK)
