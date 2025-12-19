from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from pricing_v4.models import ProductCode

class Command(BaseCommand):
    help = 'Seeds Import ProductCodes (2xxx Series)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import ProductCodes")
        self.stdout.write("=" * 60)

        codes = [
            # --- FREIGHT ---
            {
                'id': 2001, 'code': 'IMP-FRT-AIR', 
                'description': 'Import Air Freight',
                'category': 'FREIGHT', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': False
            },
            
            # --- ORIGIN CHARGES (AUD) ---
            {
                'id': 2010, 'code': 'IMP-DOC-ORIGIN', 
                'description': 'Import Documentation Fee (Origin)', 
                'category': 'DOCUMENTATION', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': False
            },
            {
                'id': 2011, 'code': 'IMP-AWB-ORIGIN', 
                'description': 'Origin AWB Fee',
                'category': 'DOCUMENTATION', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': False
            },
            {
                'id': 2012, 'code': 'IMP-AGENCY-ORIGIN',
                'description': 'Import Agency Fee (Origin)',
                'category': 'AGENCY', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': False
            },
            {
                'id': 2030, 'code': 'IMP-CTO-ORIGIN', 
                'description': 'Cargo Terminal Operator Fee (Origin)',
                'category': 'HANDLING', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': False
            },
            {
                'id': 2040, 'code': 'IMP-SCREEN-ORIGIN', 
                'description': 'X-Ray Screen Fee (Origin)',
                'category': 'SCREENING', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': False
            },
            {
                'id': 2050, 'code': 'IMP-PICKUP', 
                'description': 'Pick-Up Fee (Origin)',
                'category': 'CARTAGE', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': False
            },
            # --- DESTINATION CHARGES (PGK) - Standard Set ---
            {
                'id': 2020, 'code': 'IMP-CLEAR', 
                'description': 'Customs Clearance (Dest)',
                'category': 'CLEARANCE', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': True
            },
            {
                'id': 2021, 'code': 'IMP-AGENCY-DEST', 
                'description': 'Agency Fee (Dest)',
                'category': 'AGENCY', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': True
            },
            {
                'id': 2022, 'code': 'IMP-DOC-DEST', 
                'description': 'Documentation Fee (Dest)',
                'category': 'DOCUMENTATION', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': True
            },
            {
                'id': 2070, 'code': 'IMP-HANDLING-DEST', 
                'description': 'Handling Fee (Dest)',
                'category': 'HANDLING', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': True
            },
            {
                'id': 2071, 'code': 'IMP-LOADING-DEST', 
                'description': 'Loading Fee / Forklift (Dest)',
                'category': 'HANDLING', 'domain': 'IMPORT',
                'default_unit': 'SHIPMENT', 'is_gst_applicable': True
            },
            {
                'id': 2072, 'code': 'IMP-CARTAGE-DEST', 
                'description': 'Cartage & Delivery (Dest)',
                'category': 'CARTAGE', 'domain': 'IMPORT',
                'default_unit': 'KG', 'is_gst_applicable': True
            },
        ]

        with transaction.atomic():
            for data in codes:
                obj, created = ProductCode.objects.update_or_create(
                    id=data['id'],
                    defaults={
                        'code': data['code'],
                        'description': data['description'],
                        'category': data['category'],
                        'domain': data['domain'],
                        'default_unit': data['default_unit'],
                        'is_gst_applicable': data['is_gst_applicable'],
                        'gst_rate': Decimal('0.10'),
                        'gl_revenue_code': '4000',
                        'gl_cost_code': '5000',
                    }
                )
                action = "Created" if created else "Updated"
                self.stdout.write(f"  - {action} {data['code']}")

            # Dependent Codes (Percentage)
            # IMP-FSC-PICKUP (20% of IMP-PICKUP)
            pickup = ProductCode.objects.get(code='IMP-PICKUP')
            obj, created = ProductCode.objects.update_or_create(
                id=2060,
                defaults={
                    'code': 'IMP-FSC-PICKUP',
                    'description': 'Pick-Up Fuel Surcharge',
                    'category': 'SURCHARGE',
                    'domain': 'IMPORT',
                    'default_unit': 'PERCENT',
                    'percent_of_product_code': pickup,
                    'is_gst_applicable': False,
                    'gst_rate': Decimal('0.10'),
                    'gl_revenue_code': '4000',
                    'gl_cost_code': '5000',
                }
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  - {action} IMP-FSC-PICKUP")
            
            # IMP-FSC-CARTAGE-DEST (10% of IMP-CARTAGE-DEST)
            cartage = ProductCode.objects.get(code='IMP-CARTAGE-DEST')
            obj, created = ProductCode.objects.update_or_create(
                id=2080,
                defaults={
                    'code': 'IMP-FSC-CARTAGE-DEST',
                    'description': 'Cartage Fuel Surcharge',
                    'category': 'SURCHARGE',
                    'domain': 'IMPORT',
                    'default_unit': 'PERCENT',
                    'percent_of_product_code': cartage,
                    'is_gst_applicable': True,
                    'gst_rate': Decimal('0.10'),
                    'gl_revenue_code': '4000',
                    'gl_cost_code': '5000',
                }
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  - {action} IMP-FSC-CARTAGE-DEST")

        self.stdout.write("\n" + "="*60)
        self.stdout.write("Import ProductCodes Seeded Successfully!")
        self.stdout.write("="*60)
