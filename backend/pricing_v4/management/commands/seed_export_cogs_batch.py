from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ExportCOGS, Carrier, Agent

class Command(BaseCommand):
    help = 'Seeds Export COGS (Buy Rates) for multiple corridors'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Batch Seeding Export COGS (Buy Rates)")
        self.stdout.write("=" * 60)
        
        # Corridor Data from Rate Card
        # Format: Destination: {min_charge, [weight_breaks]}
        # Weight Breaks: (min_kg, rate)
        corridors = {
            'CNS': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "5.00"), 
                    (100, "4.90"), 
                    (200, "4.70"), 
                    (500, "4.70")
                ]
            },
            'HKG': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "20.50"), 
                    (100, "15.40"), 
                    (200, "15.40"), 
                    (500, "15.40")
                ]
            },
            'MNL': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "10.40"), 
                    (100, "8.00"), 
                    (200, "8.00"), 
                    (500, "8.00")
                ]
            },
            'HIR': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "6.35"), 
                    (100, "4.80"), 
                    (200, "4.80"), 
                    (500, "4.80")
                ]
            },
            'SIN': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "14.10"), 
                    (100, "10.60"), 
                    (200, "10.60"), 
                    (500, "10.60")
                ]
            },
            'VLI': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "14.00"), 
                    (100, "9.60"), 
                    (200, "8.70"), 
                    (500, "8.70")
                ]
            },
            'NAN': {
                'min_charge': Decimal('160.00'),
                'weight_breaks': [
                    (0, "16.30"), 
                    (100, "12.20"), 
                    (200, "12.20"), 
                    (500, "12.20")
                ]
            },
        }

        with transaction.atomic():
            carrier_px = Carrier.objects.get(code='PX')
            valid_from = date(2025, 1, 1)
            valid_until = date(2025, 12, 31)

            for dest, data in corridors.items():
                self.stdout.write(f"\nProcessing POM->{dest}...")
                
                # --- 1. FREIGHT (Variable by Corridor) ---
                wb_data = [{"min_kg": wb[0], "rate": wb[1]} for wb in data['weight_breaks']]
                
                self._create_cogs(
                    product_id=1001, # EXP-FRT-AIR
                    dest=dest,
                    carrier=carrier_px,
                    weight_breaks=wb_data,
                    min_charge=data['min_charge']
                )

                # --- 2. STANDARD SURCHARGES (Same for ALL) ---
                
                # DOC (BIC) - Flat K35
                self._create_cogs(1010, dest, carrier_px, flat_rate='35.00')
                
                # AWB (AWB) - Flat K35
                self._create_cogs(1011, dest, carrier_px, flat_rate='35.00')

                # TERM (BSC) - Flat K35
                self._create_cogs(1030, dest, carrier_px, flat_rate='35.00')

                # BUILDUP (BPC) - 0.15/kg, Min 30
                self._create_cogs(1031, dest, carrier_px, per_kg='0.15', min_charge='30.00')

                # SCREEN (MXC) - 0.17/kg + 35.00 Flat (Additive)
                self._create_cogs(1040, dest, carrier_px, per_kg='0.17', flat_rate='35.00', is_additive=True)

                # DG (RAC) - Flat K100
                self._create_cogs(1070, dest, carrier_px, flat_rate='100.00')

        self.stdout.write("\n" + "="*60)
        self.stdout.write("Batch Seeding Completed Successfully!")
        self.stdout.write("="*60)

    def _create_cogs(self, product_id, dest, carrier, 
                     flat_rate=None, per_kg=None, 
                     weight_breaks=None, min_charge=None, 
                     is_additive=False):
        
        defaults = {
            'currency': 'PGK',
            'valid_until': date(2025, 12, 31),
            'is_additive': is_additive,
            'rate_per_shipment': Decimal(flat_rate) if flat_rate else None,
            'rate_per_kg': Decimal(per_kg) if per_kg else None,
            'min_charge': Decimal(min_charge) if min_charge else None,
            'weight_breaks': weight_breaks
        }
        
        # Clean None values from defaults
        defaults = {k: v for k, v in defaults.items() if v is not None}
        
        # Ensure is_additive is explicitly set if not in defaults to avoid carry-over
        if 'is_additive' not in defaults:
            defaults['is_additive'] = False

        obj, created = ExportCOGS.objects.update_or_create(
            product_code_id=product_id,
            origin_airport='POM',
            destination_airport=dest,
            carrier=carrier,
            valid_from=date(2025, 1, 1),
            defaults=defaults
        )
        
        action = "Created" if created else "Updated"
        pc_code = ProductCode.objects.get(id=product_id).code
        self.stdout.write(f"  - {action} {pc_code}")
