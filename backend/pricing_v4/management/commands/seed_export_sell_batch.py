from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ExportSellRate

class Command(BaseCommand):
    help = 'Seeds Export SELL Rates for multiple corridors'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Batch Seeding Export SELL Rates")
        self.stdout.write("=" * 60)
        
        # Corridor Data from Rate Card (SELL)
        # Format: Destination: {min_charge, [weight_breaks]}
        # Weight Breaks: (min_kg, rate)
        corridors = {
            'CNS': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "6.25"), 
                    (100, "6.15"), 
                    (200, "5.90"), 
                    (500, "5.90")
                ]
            },
            'HKG': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "25.65"), 
                    (100, "19.25"), 
                    (200, "19.25"), 
                    (500, "19.25")
                ]
            },
            'MNL': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "13.00"), 
                    (100, "10.00"), 
                    (200, "10.00"), 
                    (500, "10.00")
                ]
            },
            'HIR': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "7.95"), 
                    (100, "6.00"), 
                    (200, "6.00"), 
                    (500, "6.00")
                ]
            },
            'SIN': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "17.65"), 
                    (100, "13.25"), 
                    (200, "13.25"), 
                    (500, "13.25")
                ]
            },
            'VLI': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "17.50"), 
                    (100, "12.00"), 
                    (200, "10.90"), 
                    (500, "10.90")
                ]
            },
            'NAN': {
                'min_charge': Decimal('200.00'),
                'weight_breaks': [
                    (0, "20.40"), 
                    (100, "15.25"), 
                    (200, "15.25"), 
                    (500, "15.25")
                ]
            },
        }

        with transaction.atomic():
            valid_from = date(2025, 1, 1)
            valid_until = date(2025, 12, 31)

            for dest, data in corridors.items():
                self.stdout.write(f"\nProcessing SELL POM->{dest}...")
                
                # --- 1. FREIGHT (Variable by Corridor) ---
                wb_data = [{"min_kg": wb[0], "rate": wb[1]} for wb in data['weight_breaks']]
                
                self._create_sell(
                    product_id=1001, # EXP-FRT-AIR
                    dest=dest,
                    weight_breaks=wb_data,
                    min_charge=data['min_charge']
                )

                # --- 2. STANDARD SURCHARGES (Same for BNE/SYD) ---
                # DOC (BIC) - Flat K50
                self._create_sell(1010, dest, flat_rate='50.00')
                
                # AWB (AWB) - Flat K50
                self._create_sell(1011, dest, flat_rate='50.00')

                # TERM (BSC) - Flat K50
                self._create_sell(1030, dest, flat_rate='50.00')

                # BUILDUP (BPC) - 0.20/kg, Min 50
                self._create_sell(1031, dest, per_kg='0.20', min_charge='50.00')

                # SCREEN (MXC) - 0.20/kg + 45.00 Flat (Additive)
                self._create_sell(1040, dest, per_kg='0.20', flat_rate='45.00', is_additive=True)
                
                # CLEARANCE - Flat K300
                self._create_sell(1020, dest, flat_rate='300.00')

                # AGENCY - Flat K250
                self._create_sell(1021, dest, flat_rate='250.00')

                # PICKUP - 1.50/kg, Min 95, Max 500
                self._create_sell(1050, dest, per_kg='1.50', min_charge='95.00', max_charge='500.00')

                # FSC PICKUP - 10%
                self._create_sell(1060, dest, percent_rate='10.00')

                # DG (RAC) - Flat K250
                self._create_sell(1070, dest, flat_rate='250.00')

        self.stdout.write("\n" + "="*60)
        self.stdout.write("Batch Seeding SELL Rates Completed Successfully!")
        self.stdout.write("="*60)

    def _create_sell(self, product_id, dest,
                     flat_rate=None, per_kg=None, 
                     weight_breaks=None, min_charge=None, max_charge=None,
                     percent_rate=None, is_additive=False):
        
        defaults = {
            'currency': 'PGK',
            'valid_until': date(2025, 12, 31),
            'is_additive': is_additive,
            'rate_per_shipment': Decimal(flat_rate) if flat_rate else None,
            'rate_per_kg': Decimal(per_kg) if per_kg else None,
            'min_charge': Decimal(min_charge) if min_charge else None,
            'max_charge': Decimal(max_charge) if max_charge else None,
            'weight_breaks': weight_breaks,
            'percent_rate': Decimal(percent_rate) if percent_rate else None
        }
        
        # Clean None values from defaults
        defaults = {k: v for k, v in defaults.items() if v is not None}
        
        # Ensure is_additive is explicitly set if not in defaults
        if 'is_additive' not in defaults:
            defaults['is_additive'] = False

        obj, created = ExportSellRate.objects.update_or_create(
            product_code_id=product_id,
            origin_airport='POM',
            destination_airport=dest,
            valid_from=date(2025, 1, 1),
            defaults=defaults
        )
        
        action = "Created" if created else "Updated"
        pc_code = ProductCode.objects.get(id=product_id).code
        self.stdout.write(f"  - {action} {pc_code}")
