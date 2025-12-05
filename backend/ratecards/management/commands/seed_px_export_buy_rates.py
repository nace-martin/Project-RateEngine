
import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent
from core.models import Location

def seed_px_buy_rates():
    print("Seeding PX Export Buy Rates...")

    # 1. Create/Get Rate Card
    card, _ = PartnerRateCard.objects.get_or_create(
        name="PX Export Buy Rates 2025",
        defaults={
            "description": "Air Niugini Export Buy Rates (Cost)",
            "currency_code": "PGK",
            "is_active": True
        }
    )

    # 2. Define Lanes (POM to Destinations)
    # We'll use the same destinations as the EFM card for now
    destinations = ["BNE", "CNS", "SYD", "SIN", "HKG", "MNL", "HIR", "NAN", "VLI"]
    origin = Location.objects.get(code="POM")
    
    lanes = []
    for dest_code in destinations:
        try:
            dest = Location.objects.get(code=dest_code)
            lane, _ = PartnerRateLane.objects.get_or_create(
                rate_card=card,
                origin_airport=origin,
                destination_airport=dest,
                mode="AIR",
                shipment_type="EXPORT",
                defaults={"is_active": True}
            )
            lanes.append(lane)
        except Location.DoesNotExist:
            print(f"Warning: Destination {dest_code} not found.")

    # 3. Seed Buy Rates (Additional Charges)
    # Note: We map these to the SAME ServiceComponents as the Sell Rates
    # so that the system can find a "Cost" for the "SECURITY_SELL" component.
    # Ideally we should have separate components (SECURITY_BUY vs SECURITY_SELL) 
    # but for now we often map Cost -> Sell Component.
    
    buy_rates = [
        # Security: 0.17/kg + 35.00 Flat
        {
            "code": "SECURITY_SELL", 
            "unit": "KG", # Primary unit
            "rate_kg": "0.17", 
            "rate_shipment": "35.00", 
            "min": None
        },
        # Documentation: 35.00 Flat
        {
            "code": "DOC_EXP_SELL", 
            "unit": "SHIPMENT", 
            "rate_kg": None, 
            "rate_shipment": "35.00", 
            "min": None
        },
        # AWB Fee: 35.00 Flat
        {
            "code": "AWB_FEE_SELL", 
            "unit": "SHIPMENT", 
            "rate_kg": None, 
            "rate_shipment": "35.00", 
            "min": None
        },
        # Terminal Fee: 35.00 Flat
        {
            "code": "TERM_EXP_SELL", 
            "unit": "SHIPMENT", 
            "rate_kg": None, 
            "rate_shipment": "35.00", 
            "min": None
        },
        # Build-Up Fee: Tiered
        # 0-99: Free, 100-2000: 0.10, >2000: 0.15. Min 30.00
        {
            "code": "BUILD_UP",
            "unit": "KG",
            "rate_kg": None, # Tiered
            "rate_shipment": None,
            "min": "30.00",
            "tiering": {
                "type": "weight_break",
                "currency": "PGK",
                "minimum_charge": "30.00",
                "breaks": [
                    {"min_kg": "0", "rate_per_kg": "0.00"},
                    {"min_kg": "100", "rate_per_kg": "0.10"},
                    {"min_kg": "2001", "rate_per_kg": "0.15"}
                ]
            }
        }
    ]

    for item in buy_rates:
        try:
            comp = ServiceComponent.objects.get(code=item["code"])
            for lane in lanes:
                PartnerRate.objects.update_or_create(
                    lane=lane,
                    service_component=comp,
                    defaults={
                        "rate_per_kg_fcy": Decimal(item["rate_kg"]) if item["rate_kg"] else None,
                        "rate_per_shipment_fcy": Decimal(item["rate_shipment"]) if item["rate_shipment"] else None,
                        "min_charge_fcy": Decimal(item["min"]) if item["min"] else None,
                        "unit": item["unit"],
                        "tiering_json": item.get("tiering")
                    }
                )
            print(f"Seeded {item['code']}")
        except ServiceComponent.DoesNotExist:
            print(f"Error: Component {item['code']} not found.")

if __name__ == '__main__':
    seed_px_buy_rates()
