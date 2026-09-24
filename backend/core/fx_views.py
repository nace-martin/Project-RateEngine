# backend/core/fx_views.py
"""FX Rate Management API Views.

Provides endpoints for:
1. Manual FX market-fact updates (Finance/Admin only)
2. FX status with staleness warning
3. Explicit automated BSP refresh
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanEditFXRates
from core.fx import upsert_market_rate

from .fx_serializers import FxStatusSerializer, ManualFxUpdateSerializer
from .models import FxSnapshot


# This remains a UI/operational warning only.  Wave 3B3 deliberately does not
# invent a hard staleness cutoff for pricing resolution.
FX_STALE_HOURS = 24
FX_REFRESH_CURRENCIES = (
    "USD",
    "AUD",
    "NZD",
    "EUR",
    "GBP",
    "SGD",
    "JPY",
    "CNY",
    "HKD",
    "PHP",
    "IDR",
    "FJD",
)
# Canonical persistence orientation: FCY/PGK (PGK per one unit of FCY).
FX_REFRESH_PAIRS = ",".join(f"{currency}:PGK" for currency in FX_REFRESH_CURRENCIES)


class ManualFxUpdateView(APIView):
    """POST /api/v4/fx/manual-update/.

    Finance/Admin users enter canonical FCY/PGK TT BUY/SELL rates.  Each entry
    becomes an authoritative ``FxMarketRate`` market fact with source MANUAL.
    A historical ``FxSnapshot`` is also created for quote-evidence compatibility.
    """

    permission_classes = [IsAuthenticated, CanEditFXRates]

    def post(self, request):
        serializer = ManualFxUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rates_data = serializer.validated_data["rates"]
        note = serializer.validated_data.get("note", "")
        now = timezone.now()
        updated_rates = []
        snapshot_rates = {}

        for currency_code, rate_info in rates_data.items():
            currency = currency_code.upper()
            market_rate = upsert_market_rate(
                as_of=now,
                base_ccy=currency,
                quote_ccy="PGK",
                tt_buy=rate_info["tt_buy"],
                tt_sell=rate_info["tt_sell"],
                source="MANUAL",
                update_snapshot=False,
            )
            snapshot_rates[currency] = {
                "tt_buy": str(market_rate.tt_buy_rate),
                "tt_sell": str(market_rate.tt_sell_rate),
                "effective_date": market_rate.effective_date.isoformat(),
                "source": market_rate.source,
            }
            updated_rates.append(
                {
                    "currency": currency,
                    "tt_buy": market_rate.tt_buy_rate,
                    "tt_sell": market_rate.tt_sell_rate,
                    "effective_date": market_rate.effective_date,
                    "source": market_rate.source,
                }
            )

        snapshot_source = f"MANUAL ({request.user.username})"
        if note:
            snapshot_source = f"{snapshot_source}: {note}"
        # FxSnapshot.source is legacy varchar(50); preserve a bounded readable
        # provenance label without changing historical snapshot schema here.
        snapshot_source = snapshot_source[:50]

        snapshot = FxSnapshot.objects.create(
            as_of_timestamp=now,
            source=snapshot_source,
            rates=snapshot_rates,
            caf_percent=Decimal("0.0"),
            fx_buffer_percent=Decimal("0.0"),
        )

        return Response(
            {
                "status": "success",
                "message": f"FX rates updated successfully for {len(updated_rates)} currencies",
                "snapshot_id": str(snapshot.id),
                "updated_rates": updated_rates,
                "updated_by": request.user.username,
                "timestamp": now.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class FxStatusView(APIView):
    """GET /api/v4/fx/status/.

    This endpoint intentionally reports the latest historical snapshot for the
    existing UI.  Pricing authority is resolved separately from FxMarketRate.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest_snapshot = FxSnapshot.objects.order_by("-as_of_timestamp").first()

        if not latest_snapshot:
            return Response(
                {
                    "rates": [],
                    "last_updated": None,
                    "source": None,
                    "is_stale": True,
                    "staleness_hours": None,
                    "staleness_warning": "No FX rates available. Please run the FX fetch or enter rates manually.",
                }
            )

        now = timezone.now()
        age = now - latest_snapshot.as_of_timestamp
        staleness_hours = age.total_seconds() / 3600
        is_stale = staleness_hours > FX_STALE_HOURS

        rates = []
        for currency_code, rate_data in (latest_snapshot.rates or {}).items():
            rates.append(
                {
                    "currency": currency_code,
                    "tt_buy": Decimal(str(rate_data.get("tt_buy", 0))),
                    "tt_sell": Decimal(str(rate_data.get("tt_sell", 0))),
                }
            )

        staleness_warning = None
        if is_stale:
            staleness_warning = (
                f"FX rates are {staleness_hours:.1f} hours old. "
                f"This exceeds the {FX_STALE_HOURS}-hour warning threshold. "
                "Please check the automated FX refresh or enter rates manually."
            )

        response_data = {
            "rates": rates,
            "last_updated": latest_snapshot.as_of_timestamp,
            "source": latest_snapshot.source,
            "is_stale": is_stale,
            "staleness_hours": round(staleness_hours, 2),
            "staleness_warning": staleness_warning,
        }

        serializer = FxStatusSerializer(response_data)
        return Response(serializer.data)


class FxRefreshView(APIView):
    """POST /api/v4/fx/refresh/.

    Triggers the BSP refresh.  The management command now persists canonical
    FxMarketRate facts and leaves historical snapshots as evidence.
    """

    permission_classes = [IsAuthenticated, CanEditFXRates]

    def post(self, request):
        stdout = StringIO()
        stderr = StringIO()

        try:
            call_command(
                "fetch_fx",
                pairs=FX_REFRESH_PAIRS,
                provider="bsp_html",
                stdout=stdout,
                stderr=stderr,
            )
        except CommandError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            detail = stderr.getvalue().strip() or str(exc) or "Failed to refresh FX rates"
            return Response(
                {
                    "detail": detail,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        latest_snapshot = FxSnapshot.objects.order_by("-as_of_timestamp").first()

        return Response(
            {
                "status": "success",
                "message": "FX rates refreshed successfully.",
                "last_updated": latest_snapshot.as_of_timestamp if latest_snapshot else None,
                "source": latest_snapshot.source if latest_snapshot else None,
                "stdout": stdout.getvalue(),
            },
            status=status.HTTP_200_OK,
        )
