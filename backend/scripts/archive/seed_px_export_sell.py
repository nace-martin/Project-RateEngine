
import os
import sys
import django
from decimal import Decimal
import json

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from parties.models import Company
from services.models import ServiceComponent
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from core.models import Airport, Country, RouteLaneConstraint, City, LocalTariff, Currency

def run():
    print("--- Seeding PX Export Prepaid D2A SELL Rates ---")

    # 1. Create Internal Supplier for Sell Rates (Project Rate Engine)
    sell_supplier, _ = Company.objects.get_or_create(
        name="Rate Engine Sell Rates",
        defaults={'is_agent': True}
    )

    # 2. Get Service Components (Ensure they exist - reusing previous)
    # We need to make sure we map the same components.
    comp_map = {
        'FRT_AIR_EXP': ServiceComponent.objects.get(code='FRT_AIR_EXP'),
        'DOC_EXP_BIC': ServiceComponent.objects.get(code='DOC_EXP_BIC'),
        'DOC_EXP_AWB': ServiceComponent.objects.get(code='DOC_EXP_AWB'),
        'DOC_EXP_LCC': ServiceComponent.objects.get(code='DOC_EXP_LCC'),
        'HND_EXP_BSC': ServiceComponent.objects.get(code='HND_EXP_BSC'),
        'HND_EXP_VA': ServiceComponent.objects.get(code='HND_EXP_VA'),
        'SEC_EXP_MXC': ServiceComponent.objects.get(code='SEC_EXP_MXC'),
        'HND_EXP_BPC': ServiceComponent.objects.get(code='HND_EXP_BPC'),
        'HND_EXP_RAC': ServiceComponent.objects.get(code='HND_EXP_RAC'),
    }

    # 3. Create Sell Rate Card
    # This acts as the "Standard Sell Rate" source.
    card_name = "PX Export Sell Rates 2024"
    rate_card, created = PartnerRateCard.objects.get_or_create(
        name=card_name,
        currency_code='PGK',
        defaults={
            'supplier': sell_supplier,
            'service_level': 'STANDARD',
            'valid_from': '2024-01-01',
        }
    )
    if not created:
         print(f"Updating Sell Rate Card: {card_name}")
    
    
    # Strategy: Remove FRT_AIR_EXP from Buy Card so Engine picks Sell Card.
    # We want to use the EXACT Sell Rates defined here.
    
    # Strategy: Remove Conflicting Components from Buy Card so Engine picks Sell Card.
    # We want to use the EXACT Sell Rates defined here for these components too.
    
    buy_card_name = "PX Export Prepaid D2A Buy Rates 2024"
    components_to_remove = [
        'FRT_AIR_EXP', 
        'DOC_EXP_AWB', 'DOC_EXP_BIC', 'SEC_EXP_MXC', 
        'HND_EXP_BSC', 'HND_EXP_BPC',
        'AGENCY_EXP', 'CLEAR_EXP', 'PICKUP_EXP', 'FUEL_SURCHARGE_EXP'
    ]
    
    try:
        buy_card = PartnerRateCard.objects.get(name=buy_card_name)
        print(f"Removing Conflicting Components from Buy Card: {buy_card_name}")
        PartnerRate.objects.filter(
            lane__rate_card=buy_card,
            service_component__code__in=components_to_remove
        ).delete()
    except PartnerRateCard.DoesNotExist:
        print(f"Buy Card {buy_card_name} not found, skipping removal.")

    pom = Airport.objects.get(iata_code='POM')
    pg_ctry = Country.objects.get(code='PG')
    pgk_curr = Currency.objects.get_or_create(code='PGK', defaults={'name': 'Kina'})[0]

    # Update FRT_AIR_EXP to be RATE_OFFER (Fixed Sell Rate)
    # This prevents Margin application on the Sell Rate logic.
    frt_comp = comp_map['FRT_AIR_EXP']
    frt_comp.cost_type = 'RATE_OFFER'
    frt_comp.save()

    # 4. Seed Freight Sell Rates
    print("\n--- Seeding Freight Sell Rates ---")
    freight_sell_data = [
        ('BNE', 'AU', 200.00, 7.90, 7.40, 7.15, 6.75),
        ('CNS', 'AU', 200.00, 6.25, 6.15, 5.90, 5.90),
        ('SYD', 'AU', 200.00, 10.00, 9.40, 8.90, 8.50),
        ('HKG', 'HK', 200.00, 25.65, 19.25, 19.25, 19.25),
        ('MNL', 'PH', 200.00, 13.00, 10.00, 10.00, 10.00),
        ('HIR', 'SB', 200.00, 7.95, 6.00, 6.00, 6.00),
        ('SIN', 'SG', 200.00, 17.65, 13.25, 13.25, 13.25),
        ('VLI', 'VU', 200.00, 17.50, 12.00, 10.90, 10.90),
        ('NAN', 'FJ', 200.00, 20.40, 15.25, 15.25, 15.25),
    ]

    for dest_code, dest_ctry_code, min_chg, norm, plus100, plus200, plus500 in freight_sell_data:
        dest_apt = Airport.objects.get(iata_code=dest_code)
        
        lane, _ = PartnerRateLane.objects.get_or_create(
            rate_card=rate_card,
            origin_airport=pom,
            destination_airport=dest_apt,
            mode='AIR',
            shipment_type='GENERAL'
        )

        tiering = {
            "type": "weight_break",
            "currency": "PGK",
            "minimum_charge": float(min_chg),
            "breaks": [
                {"min_kg": 0, "rate_per_kg": float(norm)},
                {"min_kg": 100, "rate_per_kg": float(plus100)},
                {"min_kg": 200, "rate_per_kg": float(plus200)},
                {"min_kg": 500, "rate_per_kg": float(plus500)},
            ]
        }
        
        PartnerRate.objects.filter(lane=lane, service_component=comp_map['FRT_AIR_EXP']).delete()
        PartnerRate.objects.create(
            lane=lane,
            service_component=comp_map['FRT_AIR_EXP'],
            unit='PER_KG',
            rate_per_kg_fcy=Decimal(str(norm)),
            min_charge_fcy=Decimal(str(min_chg)),
            tiering_json=tiering
        )
        print(f"Seeded Sell Freight: POM->{dest_code} {min_chg} Min, {norm}/kg Base")

    # 5. Seed Additional Export Fees (Sell)
    print("\n--- Seeding Additional Export Fees (Sell) ---")
    
    # Note: These are lane-specific in `PartnerRateCard`.
    # We attach them to ALL lanes in this Sell Card.
    all_lanes = PartnerRateLane.objects.filter(rate_card=rate_card)
    
    fees_config = [
        ('DOC_EXP_BIC', 'SHIPMENT', 50.00, None, None), # Doc Fee
        ('DOC_EXP_AWB', 'SHIPMENT', 50.00, None, None), # AWB Fee
        ('DOC_EXP_LCC', 'SHIPMENT', 100.00, None, None), # Livestock
        ('HND_EXP_BSC', 'SHIPMENT', 50.00, None, None), # Terminal Fee
        ('HND_EXP_VA',  'SHIPMENT', 10.00, None, None), # Valuable cargo
        ('HND_EXP_RAC', 'SHIPMENT', 250.00, None, None), # DG Acceptance
    ]
    
    # MXC SELL: 0.25/kg (Min 45.00) + 45.00 Flat?
    # User Says: "SELL side ... PGK 0.25/kg plus PGK 45.00"
    # Image Says: "0.20 per kg / Min 45.00"
    # User explicitly corrected image.
    # However, user said "Plus Flat Fee" for Buy (and implied mostly likely for Sell).
    # Re-reading: "The use the per kg and then add the Flat Fee ... for the SELL side Export Security Surcharge Fee it;s PGK0.25/kg plus PGK 45.00"
    # So 0.25 * kg + 45.00.
    # Is there a Min Charge on the per-kg part? Image says "Min 45.00".
    # User didn't explicitly mention Min for Sell, but usually Min applies to the variable component.
    # Let's assume Min 45.00 on the variable part + 45.00 Flat.
    # OR Min 45.00 Total?
    # Usually Min applies to weight-based calc.
    # Let's replicate strict interpretation: Rate 0.25/kg, Rate 45.00/Shipment.
    
    # BPC SELL (Build-Up):
    # Image: 0.20/kg, Min 50.00.
    # User didn't override this, so stick to Image.
    
    for lane in all_lanes:
        for code, unit, rate, min_r, max_r in fees_config:
             comp = comp_map[code]
             PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=comp,
                defaults={
                    'unit': unit,
                    'rate_per_shipment_fcy': Decimal(str(rate)) if unit == 'SHIPMENT' else None,
                    'rate_per_kg_fcy': Decimal(str(rate)) if unit != 'SHIPMENT' else None,
                    'min_charge_fcy': Decimal(str(min_r)) if min_r else None,
                }
             )
        
        # MXC Sell: 0.20/kg + K45.00 Flat Fee
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=comp_map['SEC_EXP_MXC'],
            defaults={
                'unit': 'PER_KG',
                'rate_per_kg_fcy': Decimal("0.20"),  # Corrected from 0.25
                'rate_per_shipment_fcy': Decimal("45.00"),  # Flat Fee
                'min_charge_fcy': None  # No minimum - composite formula only
 
                                                   # Engine applies min to (kg * rate).
                                                   # Then adds flat.
                                                   # So (max(kg*0.25, 45.00)) + 45.00.
                                                   # That seems like a lot (Min 90?).
                                                   # Image says "Min 45.00" next to "0.20".
                                                   # Likely Min applies to the weight calculation.
            }
        )

        # BPC Sell
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=comp_map['HND_EXP_BPC'],
            defaults={
                'unit': 'PER_KG',
                'rate_per_kg_fcy': Decimal("0.20"),
                'min_charge_fcy': Decimal("50.00")
            }
        )


    # 6. Seed Local Tariffs (Clearance & Cartage)
    print("\n--- Seeding Local Tariffs (Clearance & Cartage) ---")
    
    from ratecards.schemas import SeededRateItem
    from pydantic import ValidationError

    # We need to ensure components exist for these.
    # Appending (Export) to descriptions to ensure uniqueness
    local_comps = {
        'CLEAR_EXP': ('Customs Clearance (Export)', 'SHIPMENT'),
        'AGENCY_EXP': ('Agency Fee (Export)', 'SHIPMENT'),
        # 'CUS_ENTRY_EXP': ('Customs Entry (Export)', 'PAGE'), # REMOVED
        'PICKUP_EXP': ('Pick up Fee (Export)', 'KG'),
        'FUEL_SURCHARGE_EXP': ('Fuel Surcharge (Export)', 'PERCENTAGE'), 
    }
    
    for code, (desc, unit) in local_comps.items():
        ServiceComponent.objects.update_or_create(
            code=code,
            defaults={
                'description': desc,
                'mode': 'AIR',
                'leg': 'ORIGIN', 
                'category': 'LOCAL',
                'unit': unit,
                'cost_type': 'RATE_OFFER', # Set to RATE_OFFER for Local Charges (Fixed Sell)
                'is_active': True
            }
        )
    
    # Seed Local Rates as PartnerRates (Standard Sell Rates)
    # The Engine V3 uses PartnerRate for everything, ignoring LocalTariff logic unless specifically implemented.
    # So we attach these to the Sell Rate Card.
    
    # Refresh comp_map for Local components
    comp_map.update({
        'CLEAR_EXP': ServiceComponent.objects.get(code='CLEAR_EXP'),
        'AGENCY_EXP': ServiceComponent.objects.get(code='AGENCY_EXP'),
        'PICKUP_EXP': ServiceComponent.objects.get(code='PICKUP_EXP'),
        'FUEL_SURCHARGE_EXP': ServiceComponent.objects.get(code='FUEL_SURCHARGE_EXP'),
    })

    print("Seeding Local Charges into Sell Rate Card (With Pydantic Validation)...")

    # Define Rates to Seed
    rates_to_seed = [
        # 1. Customs Clearance
        SeededRateItem(code='CLEAR_EXP', unit='SHIPMENT', cost_type='RATE_OFFER', rate_per_shipment=Decimal("300.00"), is_fixed_sell=True),
        # 2. Agency Fee
        SeededRateItem(code='AGENCY_EXP', unit='SHIPMENT', cost_type='RATE_OFFER', rate_per_shipment=Decimal("250.00"), is_fixed_sell=True),
        # 3. Pickup Fee
        SeededRateItem(code='PICKUP_EXP', unit='PER_KG', cost_type='RATE_OFFER', rate_per_kg=Decimal("1.50"), min_charge=Decimal("95.00"), max_charge=Decimal("500.00"), is_fixed_sell=True),
    ]

    for item in rates_to_seed:
        try:
            # Pydantic validation happened at instantiation
            comp = comp_map.get(item.code)
            if not comp:
                print(f"Error: Component {item.code} not found in map.")
                continue
                
            # Enforce Cost Type on Component if Fixed Sell
            if item.is_fixed_sell:
                comp.cost_type = item.cost_type
                comp.save()
            
            for lane in all_lanes:
                PartnerRate.objects.update_or_create(
                    lane=lane,
                    service_component=comp,
                    defaults={
                        'unit': 'PER_KG' if item.unit == 'PER_KG' else 'SHIPMENT', # Simplification mapping
                        'rate_per_kg_fcy': item.rate_per_kg,
                        'rate_per_shipment_fcy': item.rate_per_shipment,
                        'min_charge_fcy': item.min_charge,
                        'max_charge_fcy': item.max_charge
                    }
                )
                
        except ValidationError as e:
            print(f"Validation Error for {item.code}: {e}")

    # 7. Set RATE_OFFER for Additional Export Fees (to skip Margin)
    # User Request: "Do not apply Margins to these Export charges"
    # Components: DOC_EXP_AWB, DOC_EXP_BIC, SEC_EXP_MXC, HND_EXP_BSC, HND_EXP_BPC
    # AGENCY_EXP handled above via SeededRateItem
    
    fixed_sell_components = [
        'DOC_EXP_AWB', 'DOC_EXP_BIC', 'SEC_EXP_MXC', 'HND_EXP_BSC', 'HND_EXP_BPC'
    ]
    for code in fixed_sell_components:
        comp = comp_map[code]
        comp.cost_type = 'RATE_OFFER' 
        comp.save()
        print(f"Updated {code} to RATE_OFFER (Fixed Sell Rate)")
         
    # 5. Fuel Surcharge (10% of Pickup)
    # Engine handles Percentage via ServiceComponent.percent_value + percent_of_component
    # V3 Logic: _is_percentage_based_component checks component.percent_of_component.
    
    fuel_comp = comp_map['FUEL_SURCHARGE_EXP']
    fuel_comp.unit = 'PERCENTAGE'
    # 10% of Pickup
    fuel_comp.percent_value = Decimal("10.00")
    
    # CRITICAL: Link to PICKUP_EXP - the engine needs this to know what to calculate 10% of
    fuel_comp.percent_of_component = comp_map['PICKUP_EXP']
    
    fuel_comp.save()
    print("Updated FUEL_SURCHARGE_EXP to 10% of PICKUP_EXP")
    
    # Note: No PartnerRate needed for Global % Components in this engine version, 
    # unless we want per-lane overrides.

    print("✓ Seeding Sell Rates Complete.")

if __name__ == "__main__":
    run()
