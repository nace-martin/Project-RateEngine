import sys
import os
from decimal import Decimal
import json

# Setup Django Environment (if running standalone)
# import django
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
# django.setup()

from parties.models import Company
from core.models import Airport
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate

def run():
    print("--- Starting Real World Rate Seed ---")

    # 1. Create the Supplier & Rate Card
    supplier, _ = Company.objects.get_or_create(
        name="Real World Logistics", 
        defaults={'company_type': "VENDOR"}
    )
    
    card, _ = PartnerRateCard.objects.get_or_create(
        name="2025 BNE-POM Import Rates (Test)",
        defaults={
            'supplier': supplier, 
            'currency_code': 'AUD',
            'valid_from': '2025-01-01'
        }
    )
    print(f"1. Rate Card Ready: {card}")

    # 2. Setup the Lane (Brisbane -> Port Moresby)
    try:
        bne_ap = Airport.objects.get(iata_code="BNE")
        pom_ap = Airport.objects.get(iata_code="POM")
    except Airport.DoesNotExist:
        print("Error: BNE or POM airports missing. Run seed_minimal_api_data first.")
        return

    lane, _ = PartnerRateLane.objects.get_or_create(
        rate_card=card,
        origin_airport=bne_ap,
        destination_airport=pom_ap,
        mode='AIR',
        shipment_type='GENERAL'
    )
    print(f"2. Lane Ready: {lane}")

    # 3. Define Simple Rates (PartnerRate records)
    # FRT_AIR is now handled separately as a tiered rate.
    simple_rates_data = [
        # --- NEW BNE Origin Charges ---
        ("PUP_BNE",  "Pick-Up Fee",               "KG",       0.26,   85.00,  "ORIGIN"),
        ("SCR",      "X-Ray Screen Fee",          "KG",       0.36,   70.00,  "ORIGIN"),
        ("CTC_ORG",  "Cargo Terminal Operator Fee", "KG",     0.30,   30.00,  "ORIGIN"),
        ("DOC_EXP",  "Export Document Fee",       "SHIPMENT", 80.00,  0.00,   "ORIGIN"),
        ("AGEN_EXP", "Export Agency Fee",         "SHIPMENT", 175.00, 0.00,   "ORIGIN"),
        ("AWB_ORG",  "Origin AWB Fee",            "SHIPMENT", 25.00,  0.00,   "ORIGIN"),
        # --- Standard Main Leg Charges ---
        ("FUEL_SUR", "Fuel & Security Surcharge","KG",       0.45,   0.00,   "MAIN"),
        ("DOC_AIR",  "Airline Documentation",   "SHIPMENT", 25.00,  0.00,   "MAIN"),
    ]

    # 4. Insert Components & Simple Rates
    for code, desc, unit, rate, min_chg, leg in simple_rates_data:
        comp, _ = ServiceComponent.objects.update_or_create(
            code=code,
            defaults={
                'description': desc, 'mode': 'AIR', 'leg': leg,
                'category': 'TRANSPORT' if 'PUP' in code else 'HANDLING',
                'cost_source': 'PARTNER_RATECARD',
                'unit': 'KG' if unit == 'KG' else 'SHIPMENT'
            }
        )
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=comp,
            defaults={
                'unit': 'PER_KG' if unit == 'KG' else 'SHIPMENT',
                'rate_per_kg_fcy': Decimal(str(rate)) if unit == 'KG' else None,
                'rate_per_shipment_fcy': Decimal(str(rate)) if unit == 'SHIPMENT' else None,
                'min_charge_fcy': Decimal(str(min_chg)) if min_chg else None
            }
        )
    print("3. Simple Rates Injected successfully.")

    # 5. Handle Tiered and Surcharge Rates
    # 5a. Tiered Air Freight Rate
    frt_air_comp, _ = ServiceComponent.objects.update_or_create(
        code="FRT_AIR",
        defaults={
            'description': "Air Freight",
            'mode': 'AIR', 'leg': 'MAIN', 'category': 'TRANSPORT',
            'cost_source': 'TIERED_RATECARD', # Indicate complex rating
            'unit': 'KG',
            'tiering_json': {
                "type": "weight_break",
                "currency": "AUD",
                "minimum_charge": "330.00",
                "breaks": [
                    { "min_kg": 45,   "rate_per_kg": "7.05" },
                    { "min_kg": 100,  "rate_per_kg": "6.75" },
                    { "min_kg": 250,  "rate_per_kg": "6.55" },
                    { "min_kg": 500,  "rate_per_kg": "6.25" },
                    { "min_kg": 1000, "rate_per_kg": "5.95" }
                ]
            }
        }
    )
    print("4. Tiered Air Freight Rate configured successfully.")

    # 5b. Pick-Up Fuel Surcharge (20% of Pick-up fee)
    puf_bne_comp, _ = ServiceComponent.objects.update_or_create(
        code="PUF_BNE",
        defaults={
            'description': "Pick-Up Fuel Surcharge (BNE)",
            'mode': 'AIR', 'leg': 'ORIGIN', 'category': 'HANDLING',
            'cost_source': 'TIERED_RATECARD', # Using TIERED_RATECARD source for this logic
            'unit': 'PERCENT', # Unit is PERCENT
            'tiering_json': {
                "type": "percent_of",
                "currency": "AUD",
                "rate": "20.0",
                "of_charge_code": "PUP_BNE" # This is the target charge
            }
        }
    )
    print("   - Pick-Up Fuel Surcharge configured successfully.")

    # 6. Update the Service Rule (Recipe)
    rule, created = ServiceRule.objects.get_or_create(
        mode='AIR', direction='IMPORT', incoterm='EXW',
        payment_term='COLLECT', service_scope='D2D',
        defaults={'description': 'Auto-created rule for BNE-POM Tiered Rates'}
    )

    if created:
        print(f"5. Created new Target Rule: {rule}")
    else:
        print(f"5. Found Target Rule: {rule}")
        
    print("   Updating ingredients...")
    
    # Get all components we just worked with
    simple_rate_codes = [item[0] for item in simple_rates_data]
    all_codes = simple_rate_codes + ["FRT_AIR", "PUF_BNE"] # <-- Add PUF_BNE here
    components = ServiceComponent.objects.filter(code__in=all_codes).order_by('code')
    
    # Clear existing components from this rule to ensure correct sequence
    ServiceRuleComponent.objects.filter(service_rule=rule).delete()
    
    for i, comp in enumerate(components):
        ServiceRuleComponent.objects.create(
            service_rule=rule,
            service_component=comp,
            sequence=i + 1,
            is_mandatory=True
        )
    print("   Success: Service Rule now includes all required charges!")

    print("--- Done ---")