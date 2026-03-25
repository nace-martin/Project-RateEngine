# backend/core/fx_views.py
"""
FX Rate Management API Views.

Provides endpoints for:
1. Manual FX rate updates (Finance/Admin only)
2. FX status with staleness checking
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
from .fx_serializers import ManualFxUpdateSerializer, FxStatusSerializer
from .models import FxSnapshot, FxRate, Currency


# Default staleness threshold in hours
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
FX_REFRESH_PAIRS = ",".join(f"PGK:{currency}" for currency in FX_REFRESH_CURRENCIES)


class ManualFxUpdateView(APIView):
    """
    POST /api/v4/fx/manual-update/
    
    Allows Finance/Admin users to manually enter FX rates when the
    automated BSP scraper fails.
    
    Creates a new FxSnapshot with source="MANUAL" and updates FxRate records.
    """
    permission_classes = [IsAuthenticated, CanEditFXRates]

    def post(self, request):
        serializer = ManualFxUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        rates_data = serializer.validated_data['rates']
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
            
            # Update FxRate records for PGK pairs
            self._update_fx_rate(currency_code_upper, rate_info, now)
        
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
            'timestamp': now.isoformat(),
        }, status=status.HTTP_201_CREATED)

    def _update_fx_rate(self, currency_code: str, rate_info: dict, timestamp):
        """Update or create FxRate records for the currency pair."""
        # Get or create currency objects
        pgk, _ = Currency.objects.get_or_create(
            code='PGK',
            defaults={'name': 'Papua New Guinean Kina', 'minor_units': 2}
        )
        fcy, _ = Currency.objects.get_or_create(
            code=currency_code,
            defaults={'name': currency_code, 'minor_units': 2}
        )
        
        # Update FCY -> PGK rate (e.g., AUD -> PGK = 2.77)
        FxRate.objects.update_or_create(
            base_currency=fcy,
            quote_currency=pgk,
            source='MANUAL',
            defaults={
                'tt_buy': rate_info['tt_buy'],
                'tt_sell': rate_info['tt_sell'],
                'last_updated': timestamp,
            }
        )


class FxStatusView(APIView):
    """
    GET /api/v4/fx/status/
    
    Returns current FX rates with staleness information.
    Available to all authenticated users.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get the latest FxSnapshot
        latest_snapshot = FxSnapshot.objects.order_by('-as_of_timestamp').first()
        
        if not latest_snapshot:
            return Response({
                'rates': [],
                'last_updated': None,
                'source': None,
                'is_stale': True,
                'staleness_hours': None,
                'staleness_warning': 'No FX rates available. Please run the FX fetch or enter rates manually.',
            })
        
        # Calculate staleness
        now = timezone.now()
        age = now - latest_snapshot.as_of_timestamp
        staleness_hours = age.total_seconds() / 3600
        is_stale = staleness_hours > FX_STALE_HOURS
        
        # Build rates list from snapshot
        rates = []
        for currency_code, rate_data in (latest_snapshot.rates or {}).items():
            rates.append({
                'currency': currency_code,
                'tt_buy': Decimal(str(rate_data.get('tt_buy', 0))),
                'tt_sell': Decimal(str(rate_data.get('tt_sell', 0))),
            })
        
        # Generate warning message if stale
        staleness_warning = None
        if is_stale:
            staleness_warning = (
                f"FX rates are {staleness_hours:.1f} hours old. "
                f"This exceeds the 24-hour threshold. "
                f"Please check the automated FX refresh or enter rates manually."
            )
        
        response_data = {
            'rates': rates,
            'last_updated': latest_snapshot.as_of_timestamp,
            'source': latest_snapshot.source,
            'is_stale': is_stale,
            'staleness_hours': round(staleness_hours, 2),
            'staleness_warning': staleness_warning,
        }
        
        serializer = FxStatusSerializer(response_data)
        return Response(serializer.data)


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
