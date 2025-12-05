
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Location, Country, Currency
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Seeds EFM POM Export Sell Rates 2025'

    def handle(self, *args, **options):
        self.stdout.write("Seeding POM Export Rates...")
        
        with transaction.atomic():
            self._seed_rates()
            
        self.stdout.write(self.style.SUCCESS("Successfully seeded POM Export Rates"))

    def _seed_rates(self):
        # 1. Get/Create Supplier
        from parties.models import Company
        supplier, _ = Company.objects.get_or_create(
            name="Express Freight Management",
            defaults={"company_type": "SUPPLIER"}
        )

        # 2. Get/Create Rate Card
        card, created = PartnerRateCard.objects.get_or_create(
            name="EFM POM Export Sell Rates 2025",
            supplier=supplier,
            defaults={
                "currency_code": "PGK",
                "service_level": "STANDARD",
            }
        )
        if created:
            self.stdout.write(f"Created Rate Card: {card.name}")
        else:
            self.stdout.write(f"Updating Rate Card: {card.name}")

        # 2. Define Rates Data
        # Destinations: BNE, CNS, SYD, SIN, HKG, MNL, HIR, NAN, VLI
        # Weight Breaks: Min, -45, +45, 100, 200, 500
        
        destinations = {
            "BNE": {"min": "180.00", "-45": "7.20", "+45": "7.20", "100": "6.75", "200": "6.50", "500": "6.15"},
            "CNS": {"min": "180.00", "-45": "5.80", "+45": "5.80", "100": "5.55", "200": "5.40", "500": "5.40"},
            "SYD": {"min": "180.00", "-45": "9.15", "+45": "9.15", "100": "8.60", "200": "8.20", "500": "7.70"},
            "SIN": {"min": "180.00", "-45": "16.10", "+45": "10.95", "100": "10.95", "200": "10.95", "500": "10.95"},
            "HKG": {"min": "180.00", "-45": "23.40", "+45": "17.65", "100": "17.65", "200": "17.65", "500": "17.65"},
            "MNL": {"min": "180.00", "-45": "11.90", "+45": "9.15", "100": "9.15", "200": "9.15", "500": "9.15"},
            "HIR": {"min": "180.00", "-45": "7.30", "+45": "5.55", "100": "5.55", "200": "5.55", "500": "5.55"},
            "NAN": {"min": "180.00", "-45": "18.60", "+45": "13.95", "100": "13.95", "200": "13.95", "500": "13.95"},
            "VLI": {"min": "180.00", "-45": "16.00", "+45": "10.95", "100": "9.90", "200": "9.90", "500": "9.90"},
        }

        # 3. Seed Freight Rates (Export Sell Rate)
        frt_component, _ = ServiceComponent.objects.get_or_create(
            code="FRT_AIR_EXP",
            defaults={
                "description": "Air Freight (Export Sell Rate)",
                "category": "FREIGHT",
                "mode": "AIR",
                "leg": "MAIN",
                "cost_type": "RATE_OFFER", # Sell Rate
                "unit": "KG",
                "is_active": True
            }
        )
        origin = Location.objects.get(code="POM")
        
        for dest_code, rates in destinations.items():
            try:
                destination = Location.objects.get(code=dest_code)
            except Location.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Location {dest_code} not found. Skipping."))
                continue

            # Create/Get Lane
            lane, _ = PartnerRateLane.objects.get_or_create(
                rate_card=card,
                origin_airport=origin.airport,
                destination_airport=destination.airport,
                defaults={
                    "mode": "AIR",
                    "shipment_type": "GENERAL",  # Fixed: Must be GENERAL per model choices
                }
            )

            # Create Tiering JSON
            tiering = {
                "type": "weight_break",
                "currency": "PGK",
                "minimum_charge": rates["min"],
                "breaks": [
                    {"min_kg": "0", "rate_per_kg": rates["-45"]},
                    {"min_kg": "45", "rate_per_kg": rates["+45"]},
                    {"min_kg": "100", "rate_per_kg": rates["100"]},
                    {"min_kg": "200", "rate_per_kg": rates["200"]},
                    {"min_kg": "500", "rate_per_kg": rates["500"]},
                ]
            }

            # Create Rate
            PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=frt_component,
                defaults={
                    "tiering_json": tiering,
                    "unit": "KG",
                    "rate_per_kg_fcy": Decimal(rates["+45"]), # Placeholder for validation, tiering takes precedence
                    "min_charge_fcy": Decimal(rates["min"]),
                }
            )
            self.stdout.write(f"Seeded rates for {dest_code}")

        # 4. Seed Additional Fees (Global for this card)
        additional_fees = [
            {"code": "DOC_EXP_SELL", "name": "Documentation Fee (Export Sell)", "unit": "SHIPMENT", "rate": "50.00", "min": None, "max": None, "cat": "DOCUMENTATION"},
            {"code": "AWB_FEE_SELL", "name": "Air Waybill Fee (Export Sell)", "unit": "SHIPMENT", "rate": "50.00", "min": None, "max": None, "cat": "DOCUMENTATION"},
            {"code": "SECURITY_SELL", "name": "Security Surcharge Fee (Export Sell)", "unit": "KG", "rate": "0.20", "min": "45.00", "max": None, "cat": "SCREENING"},
            {"code": "TERM_EXP_SELL", "name": "Terminal Fee (Export Sell)", "unit": "SHIPMENT", "rate": "50.00", "min": None, "max": None, "cat": "HANDLING"},
            {"code": "BUILD_UP", "name": "Build-Up Fee", "unit": "KG", "rate": "0.20", "min": "50.00", "max": None, "cat": "HANDLING"},
            # Origin Charges
            {"code": "CLEARANCE_SELL", "name": "Customs Clearance (Export Sell)", "unit": "SHIPMENT", "rate": "300.00", "min": None, "max": None, "cat": "CLEARANCE"},
            {"code": "AGENCY_EXP_SELL", "name": "Agency Fee (Export Sell)", "unit": "SHIPMENT", "rate": "250.00", "min": None, "max": None, "cat": "AGENCY"},
            {"code": "CUSTOMS_ENTRY", "name": "Customs Entry", "unit": "PAGE", "rate": "55.00", "min": None, "max": None, "cat": "CLEARANCE"},
            {"code": "PICKUP_SELL", "name": "Pick up Fee (Export Sell)", "unit": "KG", "rate": "1.50", "min": "95.00", "max": "500.00", "cat": "PICKUP"},
        ]

        # Ensure components exist
        for fee in additional_fees:
            comp, _ = ServiceComponent.objects.get_or_create(
                code=fee["code"],
                defaults={
                    "description": fee["name"],
                    "category": fee["cat"],
                    "mode": "AIR",
                    "leg": "ORIGIN", # Most are Origin
                    "cost_type": "RATE_OFFER",
                    "unit": fee["unit"],
                    "is_active": True
                }
            )
            
            # Add to all lanes
            lanes = PartnerRateLane.objects.filter(rate_card=card)
            for lane in lanes:
                PartnerRate.objects.update_or_create(
                    lane=lane,
                    service_component=comp,
                    defaults={
                        "rate_per_shipment_fcy": Decimal(fee["rate"]) if fee["unit"] == "SHIPMENT" else None,
                        "rate_per_kg_fcy": Decimal(fee["rate"]) if fee["unit"] == "KG" else None,
                        # Handle PAGE unit (treat as shipment for now or add specific field? 
                        # Actually, PAGE unit usually implies a quantity multiplier. 
                        # For now, let's map it to rate_per_shipment_fcy if it's a flat fee per page, 
                        # but ideally we need a quantity field. 
                        # However, the model validation might fail if unit is PAGE and we set rate_per_shipment.
                        # Let's check model validation.
                        # Wait, I didn't add validation for PAGE unit in PartnerRate.clean().
                        # So I should probably use rate_per_shipment_fcy for PAGE unit as a fallback for now, 
                        # or rate_per_kg_fcy? No, PAGE is not KG.
                        # Let's use rate_per_shipment_fcy and assume 1 page for basic quote, 
                        # or handle it as a special case.
                        # Actually, for "Customs Entry", it's "Per Page". 
                        # If I use rate_per_shipment_fcy, it's a flat fee.
                        # I'll use rate_per_shipment_fcy for now and note it.
                        "rate_per_shipment_fcy": Decimal(fee["rate"]) if fee["unit"] in ["SHIPMENT", "PAGE"] else None,
                        
                        "min_charge_fcy": Decimal(fee["min"]) if fee["min"] else None,
                        "max_charge_fcy": Decimal(fee["max"]) if fee["max"] else None,
                        "unit": fee["unit"],
                    }
                )
        
        # 5. Seed Fuel Surcharge (Percentage)
        # This is usually a ServiceComponent link, not a PartnerRate (unless it varies by partner)
        # The image says "Fuel Surcharge 10% Applies to total cartage costs".
        # We need to ensure PICKUP_FUEL component exists and is linked to PICKUP.
        
        pickup_fuel, _ = ServiceComponent.objects.get_or_create(
            code="PICKUP_FUEL",
            defaults={
                "description": "Origin Pick-Up Fuel Surcharge",
                "category": "ORIGIN",
                "unit": "PERCENT",
                "is_active": True
            }
        )
        
        pickup_comp = ServiceComponent.objects.get(code="PICKUP")
        pickup_fuel.percent_of_component = pickup_comp
        pickup_fuel.percent_value = Decimal("10.00")
        pickup_fuel.save()
        
        self.stdout.write("Seeded Additional Fees and Surcharges")
