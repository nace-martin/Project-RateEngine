from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, Surcharge

class Command(BaseCommand):
    help = 'Seeds global SELL Surcharges for Domestic Air (normalized design)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Global SELL Surcharges (Domestic Air)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Need to create AWB ProductCode if not exists
            awb_pc, _ = ProductCode.objects.get_or_create(
                id=3012,
                defaults={
                    'code': 'DOM-AWB',
                    'description': 'AWB Fee',
                    'domain': 'DOMESTIC',
                    'category': 'DOCUMENTATION',
                    'default_unit': 'FLAT',
                    'is_gst_applicable': True,
                }
            )
            
            surcharges = [
                # (ProductCode, rate_type, amount, min_charge, description)
                ('DOM-AWB', 'FLAT', '70.00', None, 'AWB Fee'),
                ('DOM-SECURITY', 'PER_KG', '0.20', '5.00', 'Security Surcharge'),
                ('DOM-FSC', 'PER_KG', '0.35', None, 'Airline Fuel Surcharge'),
            ]
            
            for code, rate_type, amount, min_chg, desc in surcharges:
                pc = ProductCode.objects.get(code=code)
                
                Surcharge.objects.update_or_create(
                    product_code=pc,
                    service_type='DOMESTIC_AIR',
                    rate_side='SELL',
                    valid_from=date(2025, 1, 1),
                    defaults={
                        'rate_type': rate_type,
                        'amount': Decimal(amount),
                        'min_charge': Decimal(min_chg) if min_chg else None,
                        'currency': 'PGK',
                        'valid_until': date(2026, 12, 31),
                        'is_active': True,
                    }
                )
                self.stdout.write(f"  - Seeded SELL: {code} = K{amount} ({rate_type})")
            
        self.stdout.write(f"\nSeeded {len(surcharges)} global SELL surcharges")
        self.stdout.write("Note: GST (10%) will be calculated at engine runtime")
