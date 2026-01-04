import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from datetime import date
from decimal import Decimal

today = date.today()
engine = ImportPricingEngine(
    quote_date=today,
    origin='BNE',
    destination='POM',
    chargeable_weight_kg=Decimal('100.0'),
    payment_term=PaymentTerm.COLLECT,
    service_scope=ServiceScope.D2D,
    tt_buy=Decimal('1.0'),
    tt_sell=Decimal('1.0'),
    caf_rate=Decimal('0.0'),
    margin_rate=Decimal('0.0')
)

result = engine.calculate_quote()

print(f"Quote Currency: {result.quote_currency}")

print(f"\nORIGIN LINES:")
for line in result.origin_lines:
    print(f"{line.product_code}: {line.sell_amount} {line.sell_currency}")

print(f"\nFREIGHT LINES:")
for line in result.freight_lines:
    print(f"{line.product_code}: {line.sell_amount} {line.sell_currency}")

print(f"\nDESTINATION LINES:")
for line in result.destination_lines:
    print(f"{line.product_code}: {line.sell_amount} {line.sell_currency}")
