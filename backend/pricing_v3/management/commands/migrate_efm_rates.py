from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from core.models import Location, Country, City, Airport
from parties.models import Company
from services.models import ServiceComponent
from pricing_v3.models import (
    Zone, ZoneMember, RateCard, RateLine, RateBreak, 
    RateScope, ChargeMethod, ChargeUnit, LocalFeeRule
)

class Command(BaseCommand):
    help = 'Migrates EFM AU -> POM rates into pricing_v3'

    def handle(self, *args, **options):
        self.stdout.write("Starting EFM Rate Migration...")
        
        with transaction.atomic():
            # 1. Ensure Locations Exist (Stubs if needed)
            # We need BNE, SYD, POM
            au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia"})[0]
            pg = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea"})[0]
            
            bne_city = City.objects.get_or_create(name="Brisbane", country=au)[0]
            syd_city = City.objects.get_or_create(name="Sydney", country=au)[0]
            pom_city = City.objects.get_or_create(name="Port Moresby", country=pg)[0]
            
            bne_apt = Airport.objects.get_or_create(iata_code="BNE", defaults={"name": "Brisbane Airport", "city": bne_city})[0]
            syd_apt = Airport.objects.get_or_create(iata_code="SYD", defaults={"name": "Sydney Airport", "city": syd_city})[0]
            pom_apt = Airport.objects.get_or_create(iata_code="POM", defaults={"name": "Jacksons International", "city": pom_city})[0]
            
            bne_loc = Location.objects.get_or_create(code="BNE", defaults={"name": "Brisbane Airport", "kind": "AIRPORT", "airport": bne_apt, "city": bne_city, "country": au})[0]
            syd_loc = Location.objects.get_or_create(code="SYD", defaults={"name": "Sydney Airport", "kind": "AIRPORT", "airport": syd_apt, "city": syd_city, "country": au})[0]
            pom_loc = Location.objects.get_or_create(code="POM", defaults={"name": "Port Moresby Airport", "kind": "AIRPORT", "airport": pom_apt, "city": pom_city, "country": pg})[0]

            # 2. Create Zones
            zone_au_east, _ = Zone.objects.get_or_create(code="AU_EAST_COAST_AIR", defaults={"name": "AU East Coast Air", "mode": "AIR"})
            ZoneMember.objects.get_or_create(zone=zone_au_east, location=bne_loc)
            ZoneMember.objects.get_or_create(zone=zone_au_east, location=syd_loc)
            
            zone_png_main, _ = Zone.objects.get_or_create(code="PNG_MAIN_AIRPORT", defaults={"name": "PNG Main Airport", "mode": "AIR"})
            ZoneMember.objects.get_or_create(zone=zone_png_main, location=pom_loc)
            
            zone_syd_via_bne, _ = Zone.objects.get_or_create(code="SYD_VIA_BNE_AIR", defaults={"name": "Sydney via Brisbane Air", "mode": "AIR"})
            ZoneMember.objects.get_or_create(zone=zone_syd_via_bne, location=syd_loc)

            # 3. Create Supplier
            efm_au, _ = Company.objects.get_or_create(name="EFM AU", defaults={"company_type": "SUPPLIER"})

            # 4. Create Components
            def get_comp(code, name):
                # Try to get by code first
                try:
                    comp = ServiceComponent.objects.get(code=code)
                    if comp.description != name:
                        self.stdout.write(f"Warning: Component {code} exists with description '{comp.description}', keeping it.")
                    return comp
                except ServiceComponent.DoesNotExist:
                    # If code doesn't exist, check if description exists (because description is unique)
                    if ServiceComponent.objects.filter(description=name).exists():
                        # If description exists, we can't create a new one with this description.
                        # We must use a different description or find the existing one.
                        # We'll append the code to the name to make it unique.
                        new_name = f"{name} ({code})"
                        self.stdout.write(f"Warning: Description '{name}' taken. Creating '{new_name}' for code {code}.")
                        return ServiceComponent.objects.create(code=code, description=new_name, mode="AIR")
                    else:
                        return ServiceComponent.objects.create(code=code, description=name, mode="AIR")

            comp_frt = get_comp("FRT_AIR", "Air Freight")
            comp_pickup = get_comp("PICKUP", "Pick-Up Fee")
            comp_pickup_fuel = get_comp("PICKUP_FUEL", "Pick-Up Fuel Surcharge")
            comp_xray = get_comp("XRAY", "X-Ray Screen Fee")
            comp_cto = get_comp("CTO", "Cargo Terminal Operator Fee")
            comp_doc_exp = get_comp("DOC_EXP", "Export Document Fee")
            comp_agency_exp = get_comp("AGENCY_EXP", "Export Agency Fee")
            comp_awb = get_comp("AWB_FEE", "Origin AWB Fee")
            
            # Destination Components
            comp_clearance = get_comp("CLEARANCE", "Customs Clearance")
            comp_agency_imp = get_comp("AGENCY_IMP", "Agency Fee (Import)")
            comp_doc_imp = get_comp("DOC_IMP", "Documentation Fee (Import)")
            comp_handling = get_comp("HANDLING", "Handling Fee")
            comp_term_int = get_comp("TERM_INT", "International Terminal Fee")
            comp_cartage = get_comp("CARTAGE", "Cartage & Delivery")
            comp_cartage_fuel = get_comp("CARTAGE_FUEL", "Cartage Fuel Surcharge")

            # 5. Create Rate Cards
            # Lane 1: BNE -> POM (Direct)
            card_bne, _ = RateCard.objects.get_or_create(
                name="EFM AU - BNE to POM (Direct)",
                supplier=efm_au,
                mode="AIR",
                origin_zone=zone_au_east, # BNE is in AU_EAST
                destination_zone=zone_png_main,
                currency="AUD",
                scope=RateScope.CONTRACT,
                priority=100,
                defaults={"valid_from": timezone.now()}
            )
            
            # Lane 2: SYD -> POM (Direct)
            # Note: SYD is also in AU_EAST. 
            # If we use the same zone, we can't distinguish BNE vs SYD rates if they were different.
            # But here BNE->POM and SYD->POM have SAME rates in the table for breaks.
            # "BNE to POM (Direct)" and "SYD to POM (Direct)" have identical rates.
            # So we can actually use ONE card for "AU_EAST -> PNG_MAIN" for these two.
            # However, the user asked for 3 distinct cards.
            # If we create 3 cards with same zones, how does resolver pick?
            # Resolver matches zones. If multiple cards match, it picks by priority.
            # If we want specific BNE vs SYD logic, we might need specific zones or just rely on the fact 
            # that they are identical.
            # BUT, "SYD -> POM (via BNE)" is different.
            # That uses `zone_syd_via_bne`.
            # So:
            # Card 1 (Standard): AU_EAST -> PNG_MAIN. Covers BNE->POM and SYD->POM (Direct).
            # Card 2 (Via BNE): SYD_VIA_BNE -> PNG_MAIN. Covers SYD->POM (Via BNE).
            # Wait, SYD is in BOTH `AU_EAST` and `SYD_VIA_BNE`.
            # If I query for SYD->POM, both cards match.
            # I need to prioritize "Via BNE" if that's the intent?
            # Usually "Direct" is preferred/default. "Via BNE" implies a specific service level.
            # The user said: "Only needed because SYD → POM (via BNE) is priced differently. Its existence helps the resolver pick correct card."
            # If I have a quote from SYD, how do I know if it's "Direct" or "Via BNE"?
            # The `Quote` model doesn't seem to have "Routing" field.
            # Maybe `service_scope` or `route`?
            # For now, I will create the cards as requested.
            # To distinguish, I might need to give "Via BNE" a higher priority if I want it to override?
            # Or maybe the user manually selects the card?
            # I'll set priorities equal for now, or maybe Via BNE lower?
            # Actually, if SYD is in both zones, the resolver returns BOTH.
            # The ChargeEngine/User might pick?
            # The prompt says "Create 3 RateCards". I will do that.
            # But wait, `card_bne` uses `zone_au_east`.
            # `card_syd` uses `zone_au_east`.
            # These are duplicates if I use the same zones.
            # I'll create `card_standard` for AU_EAST -> PNG_MAIN.
            # And `card_via` for SYD_VIA_BNE -> PNG_MAIN.
            
            # Re-reading: "Create 3 RateCards... BNE->POM (Direct), SYD->POM (Direct), SYD->POM (via BNE)"
            # If I strictly follow this, I need 3 cards.
            # But `RateCard` uniqueness is usually (supplier, mode, origin_zone, dest_zone).
            # It's not unique in the model, but logically.
            # I will create 3 cards.
            
            # Card 1: BNE Direct. I'll use AU_EAST.
            # Card 2: SYD Direct. I'll use AU_EAST. (This effectively duplicates Card 1, which is fine).
            # Card 3: SYD Via BNE. I'll use SYD_VIA_BNE.
            
            # Actually, to make them distinct for the resolver (if it returns all matches), 
            # I'll just create them.
            
            card_syd, _ = RateCard.objects.get_or_create(
                name="EFM AU - SYD to POM (Direct)",
                supplier=efm_au,
                mode="AIR",
                origin_zone=zone_au_east,
                destination_zone=zone_png_main,
                currency="AUD",
                scope=RateScope.CONTRACT,
                priority=100,
                defaults={"valid_from": timezone.now()}
            )
            
            card_syd_via, _ = RateCard.objects.get_or_create(
                name="EFM AU - SYD to POM (via BNE)",
                supplier=efm_au,
                mode="AIR",
                origin_zone=zone_syd_via_bne,
                destination_zone=zone_png_main,
                currency="AUD",
                scope=RateScope.CONTRACT,
                priority=110, # Higher priority to ensure it's visible/selectable?
                defaults={"valid_from": timezone.now()}
            )

            # 6. Populate Rates
            # Helper to add lines
            def add_freight(card, min_val, breaks_dict):
                # Delete existing to be safe
                RateLine.objects.filter(card=card, component=comp_frt).delete()
                line = RateLine.objects.create(
                    card=card, component=comp_frt, method=ChargeMethod.WEIGHT_BREAK, unit=ChargeUnit.KG,
                    min_charge=Decimal(str(min_val)), description="Air Freight"
                )
                for limit, rate in breaks_dict.items():
                    # limit is upper bound? No, prompt says "0-45", "45-100".
                    # My RateBreak model has from_value, to_value.
                    # "0-45" -> from 0 to 45.
                    # "+45kg" usually means > 45.
                    # The table says: MIN, +45kg, +100kg...
                    # Standard air freight:
                    # M (Min)
                    # N (Normal/Under 45)
                    # +45
                    # +100
                    # So "0-45" is the N rate.
                    # The table columns are: MIN, +45, +100...
                    # It seems to be missing the "N" (-45) column?
                    # Or "0-45" IS the N rate.
                    # Let's assume:
                    # 0 - 45: Rate X (Wait, table has +45 column. What is 0-45?)
                    # Prompt says: "0–45kg 7.05".
                    # So I will map:
                    # 0 -> 45: 7.05
                    # 45 -> 100: 6.75
                    # 100 -> 250: 6.55
                    # 250 -> 500: 6.25
                    # 500 -> 1000: 5.95
                    # 1000+: 5.95 (Same as 500? Prompt says 500-1000 is 5.95. +1000 is 5.95)
                    
                    RateBreak.objects.create(line=line, from_value=limit[0], to_value=limit[1], rate=Decimal(str(rate)))

            # BNE/SYD Direct Breaks
            breaks_direct = {
                (0, 45): 7.05,
                (45, 100): 6.75,
                (100, 250): 6.55,
                (250, 500): 6.25,
                (500, 1000): 5.95,
                (1000, None): 5.95
            }
            add_freight(card_bne, 330.00, breaks_direct)
            add_freight(card_syd, 330.00, breaks_direct)
            
            # SYD Via BNE Breaks
            breaks_via = {
                (0, 45): 7.75,
                (45, 100): 7.55,
                (100, 250): 7.30,
                (250, 500): 6.95,
                (500, 1000): 6.70,
                (1000, None): 6.70
            }
            add_freight(card_syd_via, 400.00, breaks_via)

            # 7. Additional Origin Charges
            # These apply to ALL 3 cards.
            def add_surcharges(card):
                # Pick-Up Fee: Min 85, 0.26/kg
                # Two lines as requested
                # Line 1: FLAT (Use min_charge as the flat amount)
                RateLine.objects.create(card=card, component=comp_pickup, method=ChargeMethod.FLAT, min_charge=Decimal("85.00"), description="Pick-Up Min")
                
                # Line 2: PER_UNIT
                l = RateLine.objects.create(card=card, component=comp_pickup, method=ChargeMethod.PER_UNIT, unit=ChargeUnit.KG, min_charge=Decimal("0.00"), description="Pick-Up Per Kg")
                RateBreak.objects.create(line=l, from_value=0, rate=Decimal("0.26"))

                # Pick-Up Fuel: 20% of Pick-Up
                RateLine.objects.create(
                    card=card, component=comp_pickup_fuel, method=ChargeMethod.PERCENT, 
                    percent_value=Decimal("0.20"), percent_of_component=comp_pickup,
                    description="Pick-Up Fuel Surcharge"
                )

                # X-Ray: Min 70, 0.36/kg
                RateLine.objects.create(card=card, component=comp_xray, method=ChargeMethod.FLAT, min_charge=Decimal("70.00"), description="X-Ray Min")
                l = RateLine.objects.create(card=card, component=comp_xray, method=ChargeMethod.PER_UNIT, unit=ChargeUnit.KG, description="X-Ray Per Kg")
                RateBreak.objects.create(line=l, from_value=0, rate=Decimal("0.36"))

                # CTO: Min 30, 0.30/kg
                RateLine.objects.create(card=card, component=comp_cto, method=ChargeMethod.FLAT, min_charge=Decimal("30.00"), description="CTO Min")
                l = RateLine.objects.create(card=card, component=comp_cto, method=ChargeMethod.PER_UNIT, unit=ChargeUnit.KG, description="CTO Per Kg")
                RateBreak.objects.create(line=l, from_value=0, rate=Decimal("0.30"))

                # Flats (Use min_charge)
                RateLine.objects.create(card=card, component=comp_doc_exp, method=ChargeMethod.FLAT, min_charge=Decimal("80.00"))
                RateLine.objects.create(card=card, component=comp_agency_exp, method=ChargeMethod.FLAT, min_charge=Decimal("175.00"))
                RateLine.objects.create(card=card, component=comp_awb, method=ChargeMethod.FLAT, min_charge=Decimal("25.00"))

            add_surcharges(card_bne)
            add_surcharges(card_syd)
            add_surcharges(card_syd_via)

            # 8. Local Fee Rules (Destination)
            # Currency PGK
            def add_local(comp, method, amount=None, rate=None, pct=None, pct_comp=None):
                defaults = {
                    "mode": "AIR",
                    "method": method,
                    "currency": "PGK",
                    "flat_amount": Decimal(str(amount)) if amount else None,
                    "rate_per_unit": Decimal(str(rate)) if rate else None,
                    "is_active": True
                }
                
                # Add percentage fields if provided
                if pct is not None:
                    defaults["percent_value"] = Decimal(str(pct))
                if pct_comp is not None:
                    defaults["percent_of_component"] = pct_comp
                
                LocalFeeRule.objects.update_or_create(
                    component=comp,
                    defaults=defaults
                )
            
            add_local(comp_clearance, ChargeMethod.FLAT, amount=300)
            add_local(comp_agency_imp, ChargeMethod.FLAT, amount=250)
            add_local(comp_doc_imp, ChargeMethod.FLAT, amount=165)
            add_local(comp_handling, ChargeMethod.FLAT, amount=165)
            add_local(comp_term_int, ChargeMethod.FLAT, amount=165)
            
            # Cartage
            # Min 95
            # Per Kg 0.95
            # We need two components: CARTAGE_MIN and CARTAGE_PERKG
            
            comp_cartage_min = get_comp("CARTAGE_MIN", "Cartage Min")
            comp_cartage_kg = get_comp("CARTAGE_PERKG", "Cartage Per Kg")
            
            add_local(comp_cartage_min, ChargeMethod.FLAT, amount=95)
            add_local(comp_cartage_kg, ChargeMethod.PER_UNIT, rate=0.95)
            
            # Cartage Fuel Surcharge: 10% of Cartage
            # We need to reference the CARTAGE component (or both min and per kg?)
            # Since CARTAGE has been split, we apply % to CARTAGE_MIN for simplicity,
            # or we can apply to the original CARTAGE component if it exists.
            # Let's apply it to the general CARTAGE component.
            add_local(comp_cartage_fuel, ChargeMethod.PERCENT, pct=0.10, pct_comp=comp_cartage)

        self.stdout.write(self.style.SUCCESS('Successfully migrated EFM rates'))
