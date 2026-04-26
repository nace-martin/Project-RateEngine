from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.category_rules import (
    is_export_destination_local_code,
    is_import_destination_local_code,
    is_import_origin_local_code,
)
from pricing_v4.models import ProductCode
from services.models import ServiceComponent


SPOT_COMPONENT_DEFAULTS = (
    {
        'code': 'SPOT_ORIGIN',
        'description': 'Spot Origin Charge',
        'mode': 'AIR',
        'leg': 'ORIGIN',
        'category': 'ACCESSORIAL',
    },
    {
        'code': 'SPOT_FREIGHT',
        'description': 'Spot Freight Charge',
        'mode': 'AIR',
        'leg': 'MAIN',
        'category': 'TRANSPORT',
    },
    {
        'code': 'SPOT_DEST',
        'description': 'Spot Destination Charge',
        'mode': 'AIR',
        'leg': 'DESTINATION',
        'category': 'ACCESSORIAL',
    },
    {
        'code': 'SPOT_CHARGE',
        'description': 'Spot Additional Charge',
        'mode': 'AIR',
        'leg': 'MAIN',
        'category': 'ACCESSORIAL',
    },
)


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
                leg = infer_component_leg(pc)
                
                # Map category
                cat_map = {
                    'FREIGHT': 'TRANSPORT',
                    'DOCUMENTATION': 'DOCUMENTATION',
                    'REGULATORY': 'DOCUMENTATION',
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

            spot_created, spot_updated = self._sync_spot_components()

        self.stdout.write(
            f"Sync complete. Created {created_count}, Updated {updated_count}. "
            f"SPOT created {spot_created}, SPOT updated {spot_updated}."
        )

    def _sync_spot_components(self):
        created_count = 0
        updated_count = 0

        for defaults in SPOT_COMPONENT_DEFAULTS:
            component, created = ServiceComponent.objects.update_or_create(
                code=defaults['code'],
                defaults={
                    **defaults,
                    'is_active': True,
                    'cost_type': 'COGS',
                    'cost_source': 'BASE_COST',
                    'unit': 'SHIPMENT',
                    'cost_currency_type': 'PGK',
                    'audience': 'BOTH',
                },
            )

            if created:
                created_count += 1
                self.stdout.write(f"Created SPOT component: {component.code}")
            else:
                updated_count += 1

        return created_count, updated_count


def infer_component_leg(product_code: ProductCode) -> str:
    code = (product_code.code or "").upper()
    description = (product_code.description or "").upper()

    if "FRT" in code:
        return "MAIN"

    if product_code.domain == ProductCode.DOMAIN_IMPORT:
        if is_import_origin_local_code(code, description):
            return "ORIGIN"
        if is_import_destination_local_code(code, description):
            return "DESTINATION"
        return "DESTINATION"

    if is_export_destination_local_code(code, description):
        return "DESTINATION"

    return "ORIGIN"
