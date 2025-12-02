from django.core.management.base import BaseCommand
from services.models import ServiceCode

class Command(BaseCommand):
    help = 'Seed initial service codes for existing components'

    def handle(self, *args, **options):
        service_codes = [
            # ORIGIN CHARGES - FX + CAF + Margin
            {
                'code': 'ORG-PICKUP-STD',
                'description': 'Origin Pickup Service (Standard)',
                'location_type': 'ORIGIN',
                'service_category': 'PICKUP',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'requires_weight': True,
                'gl_code': '4100',  # Revenue - Pickup Services
            },
            {
                'code': 'ORG-PICKUP-FUEL',
                'description': 'Origin Pickup Fuel Surcharge',
                'location_type': 'ORIGIN',
                'service_category': 'FUEL_SURCHARGE',
                'pricing_method': 'RATE_OF_BASE',  # Percentage of base pickup
                'is_taxable': True,
                'gl_code': '4110',  # Revenue - Fuel Surcharges
            },
            {
                'code': 'ORG-AWB-FEE',
                'description': 'Air Waybill Fee (Origin)',
                'location_type': 'ORIGIN',
                'service_category': 'DOCUMENTATION',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'gl_code': '4200',  # Revenue - Documentation
            },
            {
                'code': 'ORG-XRAY-SCR',
                'description': 'X-Ray Screening Fee (Origin)',
                'location_type': 'ORIGIN',
                'service_category': 'SCREENING',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'gl_code': '4300',  # Revenue - Security Services
            },
            {
                'code': 'ORG-AGENCY-STD',
                'description': 'Export Agency Fee',
                'location_type': 'ORIGIN',
                'service_category': 'AGENCY',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'gl_code': '4400',  # Revenue - Agency Services
            },
            {
                'code': 'ORG-DOC-EXP',
                'description': 'Export Documentation Fee',
                'location_type': 'ORIGIN',
                'service_category': 'DOCUMENTATION',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'gl_code': '4200',
            },
            {
                'code': 'ORG-CTO-FEE',
                'description': 'Cargo Terminal Operator Fee (Origin)',
                'location_type': 'ORIGIN',
                'service_category': 'HANDLING',
                'pricing_method': 'FX_CAF_MARGIN',
                'is_taxable': True,
                'gl_code': '4500',  # Revenue - Terminal Services
            },
            
            # FREIGHT CHARGES - Standard Rate
            {
                'code': 'FRT-AIR-BASE',
                'description': 'Air Freight (Base Rate)',
                'location_type': 'MAIN',
                'service_category': 'FREIGHT',
                'pricing_method': 'STANDARD_RATE',
                'is_taxable': True,
                'requires_weight': True,
                'requires_dimensions': True,
                'is_mandatory': True,
                'gl_code': '4000',  # Revenue - Freight
            },
            {
                'code': 'FRT-AIR-FUEL',
                'description': 'Air Freight Fuel Surcharge',
                'location_type': 'MAIN',
                'service_category': 'FUEL_SURCHARGE',
                'pricing_method': 'RATE_OF_BASE',
                'is_taxable': True,
                'gl_code': '4010',
            },
            
            # DESTINATION CHARGES - Pass-through
            {
                'code': 'DST-DELIV-STD',
                'description': 'Destination Delivery / Cartage',
                'location_type': 'DESTINATION',
                'service_category': 'DELIVERY',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'requires_weight': True,
                'gl_code': '4600',  # Revenue - Delivery Services
            },
            {
                'code': 'DST-DELIV-FUEL',
                'description': 'Cartage Fuel Surcharge',
                'location_type': 'DESTINATION',
                'service_category': 'FUEL_SURCHARGE',
                'pricing_method': 'RATE_OF_BASE',
                'is_taxable': True,
                'gl_code': '4610',
            },
            {
                'code': 'DST-CLEAR-CUS',
                'description': 'Customs Clearance',
                'location_type': 'DESTINATION',
                'service_category': 'CLEARANCE',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'gl_code': '4700',  # Revenue - Clearance Services
            },
            {
                'code': 'DST-AGENCY-IMP',
                'description': 'Import Agency Fee',
                'location_type': 'DESTINATION',
                'service_category': 'AGENCY',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'gl_code': '4400',
            },
            {
                'code': 'DST-DOC-IMP',
                'description': 'Import Documentation Fee',
                'location_type': 'DESTINATION',
                'service_category': 'DOCUMENTATION',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'gl_code': '4200',
            },
            {
                'code': 'DST-HANDL-STD',
                'description': 'Handling Fee (Destination)',
                'location_type': 'DESTINATION',
                'service_category': 'HANDLING',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'gl_code': '4500',
            },
            {
                'code': 'DST-TERM-INTL',
                'description': 'International Terminal Fee (Destination)',
                'location_type': 'DESTINATION',
                'service_category': 'HANDLING',
                'pricing_method': 'PASSTHROUGH',
                'is_taxable': True,
                'gl_code': '4500',
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for code_data in service_codes:
            code = code_data['code']
            obj, created = ServiceCode.objects.update_or_create(
                code=code,
                defaults=code_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created {code}: {code_data["description"]}'))
            else:
                updated_count += 1
                self.stdout.write(f'  Updated {code}')
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Seeded {created_count} new service codes, updated {updated_count}'))
        
        # Show summary by location
        self.stdout.write('\n--- Service Codes by Location ---')
        for location in ['ORIGIN', 'MAIN', 'DESTINATION']:
            count = ServiceCode.objects.filter(location_type=location).count()
            self.stdout.write(f'{location:15} {count} codes')
