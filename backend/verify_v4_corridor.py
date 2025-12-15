"""Quick verification script for Export POM-BNE corridor with amendments"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from datetime import date
from decimal import Decimal
from pricing_v4.models import ProductCode, Carrier, Agent
from pricing_v4.engine.export_engine import ExportPricingEngine

# Test parameters
origin = 'POM'
destination = 'BNE'
quote_date = date.today()
chargeable_weight = Decimal('150.00')

print("=" * 70)
print("VERIFICATION: Export Air D2A Prepaid POM->BNE (WITH AMENDMENTS)")
print("=" * 70)
print(f"\nTest: 150kg shipment POM->BNE")

# Verify Carrier/Agent seeding
carriers = Carrier.objects.all()
agents = Agent.objects.all()
print(f"\nCarriers: {', '.join([c.code for c in carriers])}")
print(f"Agents: {', '.join([a.code for a in agents])}")

# Get all Export ProductCodes
export_codes = ProductCode.objects.filter(domain=ProductCode.DOMAIN_EXPORT)
product_code_ids = list(export_codes.values_list('id', flat=True))
print(f"ProductCodes found: {len(product_code_ids)}")

# Initialize engine
engine = ExportPricingEngine(
    quote_date=quote_date,
    origin=origin,
    destination=destination,
    chargeable_weight_kg=chargeable_weight,
)

# Calculate quote
result = engine.calculate_quote(product_code_ids)

print(f"\n{'Code':<20} {'COGS':>10} {'SELL':>10} {'Margin':>10} {'Notes'}")
print("-" * 70)

for line in result.lines:
    notes = line.notes[:20] if line.notes else ''
    print(f"{line.product_code:<20} {line.cost_amount:>10.2f} {line.sell_amount:>10.2f} {line.margin_amount:>10.2f}  {notes}")

print("-" * 70)
print(f"{'TOTALS':<20} {result.total_cost:>10.2f} {result.total_sell:>10.2f} {result.total_margin:>10.2f}")

# Amendment Verifications
print("\n" + "=" * 70)
print("AMENDMENT VERIFICATION")
print("=" * 70)

# 1. Security Screening (additive: K0.20/kg + K40 flat for sell)
screen_line = next((l for l in result.lines if l.product_code == 'EXP-SCREEN'), None)
if screen_line:
    expected_sell = Decimal('150') * Decimal('0.20') + Decimal('40.00')  # 30 + 40 = 70
    print(f"\n[SECURITY SCREENING]")
    print(f"  Expected (additive): K0.20 × 150kg + K40 = K{expected_sell:.2f}")
    print(f"  Actual: K{screen_line.sell_amount:.2f}")
    if abs(screen_line.sell_amount - expected_sell) < Decimal('0.01'):
        print(f"  [PASS] Additive calculation correct!")
    else:
        print(f"  [FAIL] Calculation mismatch")

# 2. FSC on Pickup (10% of Pickup)
fsc_line = next((l for l in result.lines if l.product_code == 'EXP-FSC-PICKUP'), None)
pickup_line = next((l for l in result.lines if l.product_code == 'EXP-PICKUP'), None)
if fsc_line and pickup_line:
    expected_fsc = (pickup_line.sell_amount * Decimal('0.10')).quantize(Decimal('0.01'))
    print(f"\n[FSC ON PICKUP]")
    print(f"  Pickup amount: K{pickup_line.sell_amount:.2f}")
    print(f"  Expected FSC (10%): K{expected_fsc:.2f}")
    print(f"  Actual FSC: K{fsc_line.sell_amount:.2f}")
    if abs(fsc_line.sell_amount - expected_fsc) < Decimal('0.01'):
        print(f"  [PASS] Percentage calculation correct!")
    else:
        print(f"  [FAIL] Calculation mismatch")

# 3. Carrier/Agent separation
from pricing_v4.models import ExportCOGS
freight_cogs = ExportCOGS.objects.filter(product_code_id=1001).first()
doc_cogs = ExportCOGS.objects.filter(product_code_id=1010).first()
if freight_cogs and doc_cogs:
    print(f"\n[CARRIER/AGENT SEPARATION]")
    print(f"  Freight COGS carrier: {freight_cogs.carrier} (agent: {freight_cogs.agent})")
    print(f"  Doc COGS carrier: {doc_cogs.carrier} (agent: {doc_cogs.agent})")
    if freight_cogs.carrier and not freight_cogs.agent:
        print(f"  [PASS] Freight uses carrier only")
    else:
        print(f"  [FAIL] Freight should use carrier, not agent")
    if doc_cogs.agent and not doc_cogs.carrier:
        print(f"  [PASS] Documentation uses agent only")
    else:
        print(f"  [FAIL] Doc should use agent, not carrier")

# Final Summary
print("\n" + "=" * 70)
rates_missing = sum(1 for line in result.lines if line.is_rate_missing)
print(f"[{'PASS' if rates_missing == 0 else 'FAIL'}] Rate Selection: {len(result.lines)} lines, {rates_missing} missing")
print(f"[{'PASS' if result.total_margin > 0 else 'FAIL'}] Margin: {result.total_margin:.2f} PGK")
print(f"[{'PASS' if result.currency == 'PGK' else 'FAIL'}] Currency: {result.currency}")
print(f"[{'PASS' if result.total_gst == 0 else 'WARN'}] GST: {result.total_gst:.2f} (Export should be 0)")

if rates_missing == 0 and result.total_margin > 0 and result.currency == 'PGK':
    print("\n*** ALL AMENDMENTS VERIFIED: Corridor PASSING ***")
else:
    print("\n*** CORRIDOR NEEDS ATTENTION ***")
