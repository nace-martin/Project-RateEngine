from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, Surcharge

class Command(BaseCommand):
    help = 'Seeds global Surcharges for Domestic Air (normalized design)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Global Surcharges (Domestic Air)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            surcharges = [
                # (ProductCode, rate_type, amount, min_charge, description)
                ('DOM-DOC', 'FLAT', '35.00', None, 'Documentation Fee'),
                ('DOM-TERMINAL', 'FLAT', '35.00', None, 'Terminal Fee'),
                ('DOM-SECURITY', 'FLAT', '5.00', None, 'Security Surcharge'),  # Updated to Flat K5.00
                ('DOM-FSC', 'PER_KG', '0.30', None, 'Fuel Surcharge'),         # Updated to K0.30/kg
            ]
            
            for code, rate_type, amount, min_chg, desc in surcharges:
                pc = ProductCode.objects.get(code=code)
                
                Surcharge.objects.update_or_create(
                    product_code=pc,
                    service_type='DOMESTIC_AIR',
                    rate_side='COGS',  # Explicit lookup to avoid conflict with SELL
                    valid_from=date(2025, 1, 1),
                    defaults={
                        'rate_type': rate_type,
                        'amount': Decimal(amount),
                        'min_charge': Decimal(min_chg) if min_chg else None,
                        'currency': 'PGK',
                        'valid_until': date(2025, 12, 31),
                        'is_active': True,
                    }
                )
                self.stdout.write(f"  - Seeded: {code} = {amount} ({rate_type})")
            
        self.stdout.write(f"\nSeeded {len(surcharges)} global surcharges")
        self.stdout.write("These apply to ALL Domestic Air routes")
