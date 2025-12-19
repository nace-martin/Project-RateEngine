from django.core.management.base import BaseCommand
from django.db import transaction
from pricing_v4.models import ProductCode
from services.models import ServiceComponent

class Command(BaseCommand):
    help = 'Syncs V4 ProductCodes to V3 ServiceComponents'

    def handle(self, *args, **kwargs):
        self.stdout.write("Compiling V4 ProductCodes...")
        product_codes = ProductCode.objects.all()
        
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for pc in product_codes:
                # Helper to determine leg/mode
                leg = 'ORIGIN'
                if 'FRT' in pc.code:
                    leg = 'MAIN'
                elif pc.domain == 'IMPORT' and 'FRT' not in pc.code:
                    leg = 'DESTINATION'
                elif 'DEST' in pc.code:
                    leg = 'DESTINATION'
                
                # Map category
                cat_map = {
                    'FREIGHT': 'TRANSPORT',
                    'DOCUMENTATION': 'DOCUMENTATION',
                    'CUSTOMS': 'CUSTOMS',
                    'CARTAGE': 'LOCAL',
                    'SURCHARGE': 'ACCESSORIAL',
                }
                category = cat_map.get(pc.category, 'ACCESSORIAL')

                # Check for description conflict
                description = pc.description
                if ServiceComponent.objects.filter(description=description).exclude(code=pc.code).exists():
                    description = f"{description} (V4)"

                # Create/Update
                sc, created = ServiceComponent.objects.update_or_create(
                    code=pc.code,
                    defaults={
                        'description': description,
                        'mode': 'AIR',  # Assuming Air for V4 scope
                        'leg': leg,
                        'category': category,
                        'is_active': True,
                        # Defaults for others
                        'cost_type': 'COGS',
                        'cost_source': 'BASE_COST', # Placeholder
                        'unit': pc.default_unit if pc.default_unit in ['KG', 'SHIPMENT'] else 'SHIPMENT'
                    }
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(f"Created: {pc.code}")
                else:
                    updated_count += 1
                    # self.stdout.write(f"Updated: {pc.code}")
        
        self.stdout.write(f"Sync complete. Created {created_count}, Updated {updated_count}.")
