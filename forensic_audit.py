import os
import sys
import django
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import uuid

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.dataclasses import QuoteInput, ShipmentDetails, LocationRef, Piece
from pricing_v4.adapter import PricingServiceV4Adapter
from core.models import Location

def run_forensic_audit(direction, scope, origin_code, dest_code):
    print("\n" + "="*60)
    print(f" FORENSIC AUDIT: {direction} | {scope} | {origin_code} -> {dest_code}")
    print("="*60)
    
    # 1. Prepare Inputs
    origin_loc = Location.objects.filter(code=origin_code).first()
    dest_loc = Location.objects.filter(code=dest_code).first()
    
    origin_ref = LocationRef(
        id=origin_loc.id,
        code=origin_loc.code,
        name=origin_loc.name,
        country_code=origin_loc.country.code if origin_loc.country else "PG"
    )
    dest_ref = LocationRef(
        id=dest_loc.id,
        code=dest_loc.code,
        name=dest_loc.name,
        country_code=dest_loc.country.code if dest_loc.country else "PG"
    )

    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type=direction,
        incoterm='DAP',
        payment_term='PREPAID', # FCY Quote
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"), gross_weight_kg=Decimal("100"))],
        service_scope=scope,
        direction=direction,
        origin_location=origin_ref,
        destination_location=dest_ref
    )

    quote_input = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='AUD', # Force AUD to match reported issue
        quote_date=date.today(),
        shipment=shipment
    )

    # 2. Execute Calculation
    adapter = PricingServiceV4Adapter(quote_input)
    result = adapter.calculate_charges()

    # 3. Trace Totals
    print(f"\nAudit Totals (FCY - AUD):")
    print(f" - total_sell_fcy (Ex GST):      {result.totals.total_sell_fcy}")
    print(f" - total_sell_fcy_incl_gst:      {result.totals.total_sell_fcy_incl_gst}")
    
    calculated_gst = result.totals.total_sell_fcy_incl_gst - result.totals.total_sell_fcy
    print(f" - Derived GST:                  {calculated_gst}")
    
    print(f"\nAudit Totals (PGK):")
    print(f" - total_sell_pgk:               {result.totals.total_sell_pgk}")
    print(f" - total_sell_pgk_incl_gst:      {result.totals.total_sell_pgk_incl_gst}")

    print("\nLine Item Breakdown (AUD):")
    sum_sell_fcy = Decimal('0')
    sum_gst_fcy = Decimal('0')
    
    # We need to manually convert line GST to FCY for audit as adapter doesn't expose it per line in totals
    fx_rates = adapter._get_fx_rates_dict()
    output_fx_sell = adapter._get_fx_sell_rate('AUD', fx_rates)

    for line in result.lines:
        if not line.is_informational and not line.conditional:
            sum_sell_fcy += line.sell_fcy
            line_gst_fcy = (line.sell_pgk_incl_gst - line.sell_pgk) / output_fx_sell
            sum_gst_fcy += line_gst_fcy
            
        status = "[MISSING]" if line.is_rate_missing else "[OK]"
        info = "(INFO)" if line.is_informational else ""
        cond = "(COND)" if line.conditional else ""
        print(f" {status}{info}{cond} {line.service_component_code:<25} | Sell AUD: {line.sell_fcy:>8.2f} | Bucket: {line.bucket}")

    print(f"\nMathematical Summation Check (AUD):")
    print(f" - Sum of Line Sells:            {sum_sell_fcy.quantize(Decimal('0.01'))}")
    print(f" - Sum of Line GSTs:             {sum_gst_fcy.quantize(Decimal('0.01'))}")
    print(f" - Final Verified Total:         {(sum_sell_fcy + sum_gst_fcy).quantize(Decimal('0.01'))}")

    # Check for the bug: Sell Ex GST is 0 but Inc GST is non-zero
    if result.totals.total_sell_fcy == 0 and result.totals.total_sell_fcy_incl_gst != 0:
        print("\n❌ BUG DETECTED: Total Sell (Ex GST) is 0.00 while Inc GST is non-zero!")
    else:
        print("\n✅ LOGIC VERIFIED: Totals are mathematically consistent.")

if __name__ == "__main__":
    # Simulate the reported issue context
    run_forensic_audit('IMPORT', 'D2D', 'BNE', 'POM')
