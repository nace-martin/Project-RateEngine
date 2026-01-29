# backend/pricing_v4/management/commands/seed_export_sell_fcy.py
"""
Seeds Export SELL Rates in FCY (USD/AUD) for Export Collect scenarios.

Based on the "EXPORT SELL - PREPAID D2A" rate card (which is actually used for Collect quotes).

Currency Rules:
- USD: All non-AU destinations (SIN, HKG, MNL, etc.)
- AUD: AU destinations only (BNE, SYD, CNS)
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ExportSellRate


class Command(BaseCommand):
    help = 'Seeds Export SELL Rates in USD/AUD for Export Collect quotes'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Export Collect FCY Sell Rates (USD/AUD)")
        self.stdout.write("=" * 60)
        
        # Air Freight Rates from spreadsheet
        # Format: destination -> {country, currency, min, weight_breaks[(min_kg, rate)]}
        air_freight_rates = {
            # Australia destinations (AUD) - from EXPORT SELL PREPAID D2A rate card
            'BNE': {'country': 'AU', 'currency': 'AUD', 'min': '75.00', 
                    'breaks': [(0, '2.90'), (100, '2.75'), (200, '2.65'), (500, '2.50')]},
            'CNS': {'country': 'AU', 'currency': 'AUD', 'min': '75.00',
                    'breaks': [(0, '2.30'), (100, '2.25'), (200, '2.20'), (500, '2.20')]},
            'SYD': {'country': 'AU', 'currency': 'AUD', 'min': '75.00',
                    'breaks': [(0, '3.70'), (100, '3.45'), (200, '3.30'), (500, '3.15')]},
            
            # Non-AU destinations (USD) - from USD rate card
            'HKG': {'country': 'HK', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '6.80'), (100, '6.50'), (200, '6.50'), (500, '6.50')]},
            'MNL': {'country': 'PH', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '3.45'), (100, '3.00'), (200, '2.50'), (500, '2.50')]},
            'HIR': {'country': 'SB', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '2.15'), (100, '2.00'), (200, '2.00'), (500, '2.00')]},
            'SIN': {'country': 'SG', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '4.70'), (100, '4.50'), (200, '4.00'), (500, '4.00')]},
            'VLI': {'country': 'VU', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '4.65'), (100, '4.00'), (200, '3.25'), (500, '3.25')]},
            'NAN': {'country': 'FJ', 'currency': 'USD', 'min': '60.00',
                    'breaks': [(0, '5.45'), (100, '5.00'), (200, '5.00'), (500, '5.00')]},
        }
        
        # USD Surcharges (for non-AU destinations)
        usd_surcharges = {
            # ProductCode ID: (rate_type, value, min, max, notes)
            1020: ('flat', '105.00', None, None, 'Customs Clearance'),
            1021: ('flat', '90.00', None, None, 'Agency Fee'),
            1010: ('flat', '15.00', None, None, 'Documentation'),
            1011: ('flat', '15.00', None, None, 'AWB Fee'),
            1032: ('flat', '15.00', None, None, 'Export Handling Fee'),
            1030: ('flat', '15.00', None, None, 'Terminal Fee'),
            1050: ('per_kg', '0.50', '50.00', '250.00', 'Pickup Fee'),
            1060: ('percent', '10.00', None, None, 'Fuel Surcharge on Pickup'),
            1040: ('per_kg_flat', '0.05', None, '12.00', 'Security Surcharge Fee'),
            1031: ('per_kg', '0.05', '50.00', None, 'Build-Up Fee'),
            1070: ('flat', '80.00', None, None, 'Dangerous Goods Acceptance'),
        }
        
        # AUD Surcharges (for AU destinations) - DIFFERENT VALUES
        aud_surcharges = {
            # ProductCode ID: (rate_type, value, min, max, notes)
            1020: ('flat', '130.00', None, None, 'Customs Clearance'),
            1021: ('flat', '120.00', None, None, 'Agency Fee'),
            1010: ('flat', '60.00', None, None, 'Documentation'),
            1011: ('flat', '60.00', None, None, 'AWB Fee'),
            1032: ('flat', '60.00', None, None, 'Export Handling Fee'),
            1030: ('flat', '19.00', None, None, 'Terminal Fee'),
            1050: ('per_kg', '0.50', '50.00', '300.00', 'Pickup Fee'),
            1060: ('percent', '10.00', None, None, 'Fuel Surcharge on Pickup'),
            1040: ('per_kg_flat', '0.10', None, '19.00', 'Security Surcharge Fee'),
            1031: ('per_kg', '0.10', '19.00', None, 'Build-Up Fee'),
            1070: ('flat', '100.00', None, None, 'Dangerous Goods Acceptance'),
        }
        
        with transaction.atomic():
            valid_from = date(2026, 1, 1)
            valid_until = date(2026, 12, 31)
            
            for dest, data in air_freight_rates.items():
                currency = data['currency']
                self.stdout.write(f"\nProcessing {currency} rates for POM->{dest}...")
                
                # --- 1. AIR FREIGHT (Variable by corridor) ---
                wb_data = [{"min_kg": wb[0], "rate": wb[1]} for wb in data['breaks']]
                
                self._create_sell(
                    product_id=1001,
                    dest=dest,
                    currency=currency,
                    weight_breaks=wb_data,
                    min_charge=data['min']
                )
                
                # --- 2. SURCHARGES - Use appropriate rate card based on currency ---
                surcharges = aud_surcharges if currency == 'AUD' else usd_surcharges
                for pc_id, (rate_type, value, min_val, max_val, notes) in surcharges.items():
                    if rate_type == 'flat':
                        self._create_sell(pc_id, dest, currency, flat_rate=value)
                    elif rate_type == 'per_kg':
                        self._create_sell(pc_id, dest, currency, per_kg=value, 
                                        min_charge=min_val, max_charge=max_val)
                    elif rate_type == 'percent':
                        self._create_sell(pc_id, dest, currency, percent_rate=value)
                    elif rate_type == 'per_kg_flat':
                        # Security surcharge: per_kg + flat fee (additive)
                        self._create_sell(pc_id, dest, currency, per_kg=value,
                                        flat_rate=max_val, is_additive=True)
                
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("FCY Sell Rate Seeding Complete!")
        self.stdout.write("=" * 60)
        
        # Summary
        self.stdout.write("\nSummary:")
        self.stdout.write(f"  AUD destinations: BNE, CNS, SYD")
        self.stdout.write(f"  USD destinations: HKG, MNL, HIR, SIN, VLI, NAN")

    def _create_sell(self, product_id, dest, currency,
                     flat_rate=None, per_kg=None,
                     weight_breaks=None, min_charge=None, max_charge=None,
                     percent_rate=None, is_additive=False):
        
        defaults = {
            'valid_until': date(2026, 12, 31),
            'is_additive': is_additive,
            'rate_per_shipment': Decimal(flat_rate) if flat_rate else None,
            'rate_per_kg': Decimal(per_kg) if per_kg else None,
            'min_charge': Decimal(min_charge) if min_charge else None,
            'max_charge': Decimal(max_charge) if max_charge else None,
            'weight_breaks': weight_breaks,
            'percent_rate': Decimal(percent_rate) if percent_rate else None,
        }
        
        # Clean None values
        defaults = {k: v for k, v in defaults.items() if v is not None}
        
        if 'is_additive' not in defaults:
            defaults['is_additive'] = False
        
        # Use FCY valid_from date to distinguish from PGK rates
        fcy_valid_from = date(2026, 1, 2)  # One day after PGK rates
        
        obj, created = ExportSellRate.objects.update_or_create(
            product_code_id=product_id,
            origin_airport='POM',
            destination_airport=dest,
            currency=currency,
            valid_from=fcy_valid_from,
            defaults=defaults
        )
        
        action = "Created" if created else "Updated"
        pc_code = ProductCode.objects.get(id=product_id).code
        self.stdout.write(f"  - {action} {pc_code} ({currency})")
