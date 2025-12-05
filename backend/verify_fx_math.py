import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from core.models import FxSnapshot

def verify_math():
    try:
        snapshot = FxSnapshot.objects.latest('as_of_timestamp')
        rates = snapshot.rates
        
        print(f"Using Snapshot from: {snapshot.as_of_timestamp}")
        print(f"Raw Rates: {rates}")
        
        # USD Calculation
        usd_sell_rate = Decimal(str(rates['USD']['tt_sell']))
        pgk_to_usd = Decimal("1.0") / usd_sell_rate
        print(f"\nUSD Analysis:")
        print(f"  TT Sell (PGK per USD): {usd_sell_rate}")
        print(f"  1 PGK = {pgk_to_usd:.4f} USD")
        
        # AUD Calculation
        aud_sell_rate = Decimal(str(rates['AUD']['tt_sell']))
        pgk_to_aud = Decimal("1.0") / aud_sell_rate
        print(f"\nAUD Analysis:")
        print(f"  TT Sell (PGK per AUD): {aud_sell_rate}")
        print(f"  1 PGK = {pgk_to_aud:.4f} AUD")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_math()
