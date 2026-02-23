import os
import sys
import django
from decimal import Decimal
from datetime import date
import uuid

# Setup Django environment
BACKEND_DIR = os.path.join(os.getcwd(), 'dev', 'Project-RateEngine', 'backend')
if not os.path.exists(BACKEND_DIR):
    BACKEND_DIR = os.path.join(os.getcwd(), 'backend')

sys.path.append(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote, QuoteLine
from core.dataclasses import QuoteInput, ShipmentDetails, LocationRef, Piece
from pricing_v4.adapter import PricingServiceV4Adapter
from core.models import Location
from parties.models import Company

def recalculate_specific_quote(quote_number):
    print("\n--- RECALCULATING QUOTE: " + quote_number + " ---")
    
    try:
        q = Quote.objects.get(quote_number=quote_number)
        req = q.request_details_json
        
        origin_loc = Location.objects.get(id=req['origin_location_id'])
        dest_loc = Location.objects.get(id=req['destination_location_id'])
        
        origin_ref = LocationRef(
            id=origin_loc.id, code=origin_loc.code, name=origin_loc.name,
            country_code=origin_loc.country.code if origin_loc.country else "PG"
        )
        dest_ref = LocationRef(
            id=dest_loc.id, code=dest_loc.code, name=dest_loc.name,
            country_code=dest_loc.country.code if dest_loc.country else "PG"
        )

        shipment = ShipmentDetails(
            mode=req['mode'], shipment_type=q.shipment_type, incoterm=req['incoterm'],
            payment_term=req['payment_term'], is_dangerous_goods=req['is_dangerous_goods'],
            pieces=[Piece(
                pieces=int(p['pieces']), length_cm=Decimal(p['length_cm']),
                width_cm=Decimal(p['width_cm']), height_cm=Decimal(p['height_cm']),
                gross_weight_kg=Decimal(p['gross_weight_kg'])
            ) for p in req['dimensions']],
            service_scope=req['service_scope'], direction=q.shipment_type,
            origin_location=origin_ref, destination_location=dest_ref
        )

        quote_input = QuoteInput(
            customer_id=uuid.UUID(req['customer_id']),
            contact_id=uuid.UUID(req['contact_id']),
            output_currency=q.output_currency,
            quote_date=date.today(),
            shipment=shipment
        )

        adapter = PricingServiceV4Adapter(quote_input)
        calculated_charges = adapter.calculate_charges()
        
        version = q.versions.order_by('-version_number').first()
        t = version.totals
        
        print(f"OLD total_sell_fcy: {t.total_sell_fcy}")
        
        # Update Totals
        t.total_cost_pgk = calculated_charges.totals.total_cost_pgk
        t.total_sell_pgk = calculated_charges.totals.total_sell_pgk
        t.total_sell_pgk_incl_gst = calculated_charges.totals.total_sell_pgk_incl_gst
        t.total_sell_fcy = calculated_charges.totals.total_sell_fcy
        t.total_sell_fcy_incl_gst = calculated_charges.totals.total_sell_fcy_incl_gst
        t.save()
        
        # Update Lines (delete and recreate to ensure all new fields are saved)
        version.lines.all().delete()
        for l in calculated_charges.lines:
            QuoteLine.objects.create(
                quote_version=version,
                service_component_id=l.service_component_id,
                cost_pgk=l.cost_pgk,
                cost_fcy=l.cost_fcy,
                cost_fcy_currency=l.cost_fcy_currency,
                sell_pgk=l.sell_pgk,
                sell_pgk_incl_gst=l.sell_pgk_incl_gst,
                sell_fcy=l.sell_fcy,
                sell_fcy_incl_gst=l.sell_fcy_incl_gst,
                sell_fcy_currency=l.sell_fcy_currency,
                exchange_rate=l.exchange_rate,
                cost_source=l.cost_source,
                cost_source_description=l.cost_source_description,
                is_rate_missing=l.is_rate_missing,
                leg=l.leg,
                bucket=l.bucket,
                gst_category=l.gst_category,
                gst_rate=l.gst_rate,
                gst_amount=l.gst_amount, # THIS IS THE KEY FIELD
                is_informational=l.is_informational,
                conditional=l.conditional
            )
        
        print(f"NEW total_sell_fcy: {t.total_sell_fcy}")
        print(f"NEW total_sell_fcy_incl_gst: {t.total_sell_fcy_incl_gst}")
        
        print("\n--- Corrected Lines with GST ---")
        for line in QuoteLine.objects.filter(quote_version=version).select_related('service_component'):
            code = line.service_component.code if line.service_component else "MANUAL"
            print(f" {code:<20} | Sell AUD: {line.sell_fcy:>8.2f} | GST AUD: {line.gst_amount:>8.2f}")

    except Exception as e:
        print(f"Error during recalculation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    recalculate_specific_quote('DRAFT-BF1384B9')
