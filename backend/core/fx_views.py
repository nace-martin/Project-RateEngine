# backend/core/fx_views.py
"""
FX Rate Management API Views.

Provides endpoints for:
1. Manual FX rate updates (Finance/Admin only)
2. Market FX status with effective dates and source provenance
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanEditFXRates
from .fx_serializers import ManualFxUpdateSerializer
from .models import FxSnapshot
from core.fx_market_models import FxMarketRate


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
FX_REFRESH_PAIRS = ",".join(f"PGK:{currency}" for currency in FX_REFRESH_CURRENCIES)


class ManualFxUpdateView(APIView):
    """
    POST /api/v4/fx/manual-update/
    
    Allows Finance/Admin users to manually enter FX rates when the
    automated BSP scraper fails.
    
    Creates a new FxSnapshot and writes FxMarketRate facts.
    """
    permission_classes = [IsAuthenticated, CanEditFXRates]

    @transaction.atomic
    def post(self, request):
        serializer = ManualFxUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        rates_data = serializer.validated_data['rates']
        effective_date = serializer.validated_data['effective_date']
        note = serializer.validated_data.get('note', '')
        
        now = timezone.now()
        updated_rates = []
        
        # Build the FxSnapshot rates blob
        snapshot_rates = {}
        for currency_code, rate_info in rates_data.items():
            currency_code_upper = currency_code.upper()
            snapshot_rates[currency_code_upper] = {
                'tt_buy': str(rate_info['tt_buy']),
                'tt_sell': str(rate_info['tt_sell']),
            }
            updated_rates.append({
                'currency': currency_code_upper,
                'tt_buy': rate_info['tt_buy'],
                'tt_sell': rate_info['tt_sell'],
            })
            
            # Update FCY/PGK market facts.
            self._update_fx_rate(currency_code_upper, rate_info, effective_date)
        
        # Create immutable FxSnapshot
        snapshot = FxSnapshot.objects.create(
            as_of_timestamp=now,
            source=f"MANUAL ({request.user.username})" + (f": {note}" if note else ""),
            rates=snapshot_rates,
            caf_percent=Decimal('0.0'),
            fx_buffer_percent=Decimal('0.0'),
        )
        
        return Response({
            'status': 'success',
            'message': f'FX rates updated successfully for {len(updated_rates)} currencies',
            'snapshot_id': str(snapshot.id),
            'updated_rates': updated_rates,
            'updated_by': request.user.username,
            'effective_date': effective_date.isoformat(),
            'timestamp': now.isoformat(),
        }, status=status.HTTP_201_CREATED)

    def _update_fx_rate(self, currency_code: str, rate_info: dict, effective_date):
        """Update or create FxMarketRate records for the currency pair."""
        from decimal import ROUND_HALF_UP

        tt_buy = Decimal(str(rate_info['tt_buy']))
        tt_sell = Decimal(str(rate_info['tt_sell']))
        mid = ((tt_buy + tt_sell) / Decimal('2')).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
        FxMarketRate.objects.update_or_create(
            base_currency=currency_code.upper(),
            quote_currency='PGK',
            effective_date=effective_date,
            source='MANUAL',
            defaults={
                'tt_buy_rate': tt_buy,
                'tt_sell_rate': tt_sell,
                'mid_rate': mid,
            },
        )


class FxStatusView(APIView):
    """Show current market facts without applying an unapproved staleness rule."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from pricing_v4.services.fx_resolver import (
            AmbiguousFxSourceError,
            resolve_market_fx_pair,
        )

        today = timezone.localdate()
        rates = []
        ambiguous = []
        for currency in (
            FxMarketRate.objects.filter(quote_currency='PGK', effective_date__lte=today)
            .values_list('base_currency', flat=True).distinct()
        ):
            try:
                pair = resolve_market_fx_pair(currency, 'PGK', today)
            except AmbiguousFxSourceError:
                ambiguous.append(currency)
                continue
            rates.append({
                'currency': currency,
                'tt_buy': pair.tt_buy,
                'tt_sell': pair.tt_sell,
                'effective_date': pair.effective_date,
                'source': pair.source,
            })

        dates = [rate['effective_date'] for rate in rates]
        warning = 'No approved FX staleness threshold; review each effective date.'
        if ambiguous:
            warning += f" Ambiguous source for: {', '.join(sorted(ambiguous))}."
        return Response({
            'rates': rates,
            'last_updated': max(dates).isoformat() if dates else None,
            'source': 'FxMarketRate' if dates else None,
            'is_stale': None,
            'staleness_hours': None,
            'staleness_warning': warning if dates or ambiguous else 'No market FX rates available.',
        })


class FxRefreshView(APIView):
    """
    POST /api/v4/fx/refresh/

    Triggers the automated BSP FX refresh and returns the latest snapshot metadata.
    """
    permission_classes = [IsAuthenticated, CanEditFXRates]

    def post(self, request):
        stdout = StringIO()
        stderr = StringIO()

        try:
            call_command(
                'fetch_fx',
                pairs=FX_REFRESH_PAIRS,
                provider='bsp_html',
                stdout=stdout,
                stderr=stderr,
            )
        except CommandError as exc:
            return Response(
                {
                    'detail': str(exc),
                    'stdout': stdout.getvalue(),
                    'stderr': stderr.getvalue(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            detail = stderr.getvalue().strip() or str(exc) or 'Failed to refresh FX rates'
            return Response(
                {
                    'detail': detail,
                    'stdout': stdout.getvalue(),
                    'stderr': stderr.getvalue(),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        latest_snapshot = FxSnapshot.objects.order_by('-as_of_timestamp').first()

        return Response(
            {
                'status': 'success',
                'message': 'FX rates refreshed successfully.',
                'last_updated': latest_snapshot.as_of_timestamp if latest_snapshot else None,
                'source': latest_snapshot.source if latest_snapshot else None,
                'stdout': stdout.getvalue(),
            },
            status=status.HTTP_200_OK,
        )
