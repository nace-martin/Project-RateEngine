from django.core.management.base import BaseCommand
from django.db import transaction
from pricing_v4.models import ProductCode

class Command(BaseCommand):
    help = 'Seeds ProductCodes for Domestic Air (3xxx series)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Domestic ProductCodes (3xxx series)")
        self.stdout.write("=" * 60)

        codes = [
            # Core Freight
            (3001, 'DOM-FRT-AIR', 'Domestic Air Freight', 'FREIGHT', 'PER_KG', False),
            
            # Documentation & Terminal
            (3010, 'DOM-DOC', 'Documentation Fee', 'DOCUMENTATION', 'FLAT', False),
            (3011, 'DOM-TERMINAL', 'Terminal Fee', 'TERMINAL', 'FLAT', False),
            (3012, 'DOM-AWB', 'AWB Fee', 'DOCUMENTATION', 'FLAT', False),
            
            # Security
            (3020, 'DOM-SECURITY', 'Security Surcharge', 'SECURITY', 'PER_KG', False),
            (3021, 'DOM-DG-HANDLING', 'DG Handling Fee', 'HANDLING', 'FLAT', False),
            
            # Fuel Surcharge
            (3030, 'DOM-FSC', 'Fuel Surcharge', 'SURCHARGE', 'PER_KG', False),
            
            # Handling
            (3040, 'DOM-HANDLING-ORIGIN', 'Origin Handling', 'HANDLING', 'PER_KG', False),
            (3041, 'DOM-HANDLING-DEST', 'Destination Handling', 'HANDLING', 'PER_KG', False),
            
            # Cartage
            (3050, 'DOM-PICKUP', 'Pickup / Collection', 'CARTAGE', 'PER_KG', False),
            (3051, 'DOM-DELIVERY', 'Delivery', 'CARTAGE', 'PER_KG', False),
            
            # Special Cargo Multipliers (stored as reference, applied as multiplier)
            (3100, 'DOM-EXPRESS', 'Express Cargo Surcharge', 'SPECIAL', 'PERCENT', False),
            (3101, 'DOM-VALUABLE', 'Valuable Cargo Surcharge', 'SPECIAL', 'PERCENT', False),
            (3102, 'DOM-LIVE-ANIMAL', 'Live Animal Surcharge', 'SPECIAL', 'PERCENT', False),
            (3103, 'DOM-OVERSIZE', 'Oversize Cargo Surcharge', 'SPECIAL', 'PERCENT', False),
            
            # VAT
            (3200, 'DOM-VAT', 'VAT (10%)', 'TAX', 'PERCENT', True),
        ]

        with transaction.atomic():
            for id, code, desc, cat, unit, is_gst in codes:
                pc, created = ProductCode.objects.update_or_create(
                    id=id,
                    defaults={
                        'code': code,
                        'description': desc,
                        'domain': 'DOMESTIC',
                        'category': cat,
                        'default_unit': unit,
                        'is_gst_applicable': is_gst,
                    }
                )
                status = "Created" if created else "Updated"
                self.stdout.write(f"  {status}: {code} ({desc})")
        
        self.stdout.write(f"\nSeeded {len(codes)} Domestic ProductCodes")
