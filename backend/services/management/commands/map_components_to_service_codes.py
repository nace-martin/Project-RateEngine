from django.core.management.base import BaseCommand
from services.models import ServiceComponent, ServiceCode

class Command(BaseCommand):
    help = 'Map existing ServiceComponents to ServiceCodes'

    def handle(self, *args, **options):
        # Define mappings from component code to service code
        COMPONENT_TO_SERVICE_CODE = {
            # Origin components
            'PICKUP': 'ORG-PICKUP-STD',
            'PUP_BNE': 'ORG-PICKUP-STD',
            'PKUP_ORG': 'ORG-PICKUP-STD',
            'PICKUP_FUEL': 'ORG-PICKUP-FUEL',
            'PUF_BNE': 'ORG-PICKUP-FUEL',
            'AWB_FEE': 'ORG-AWB-FEE',
            'AWB_ORG': 'ORG-AWB-FEE',
            'XRAY': 'ORG-XRAY-SCR',
            'SCR': 'ORG-XRAY-SCR',
            'AGENCY_EXP': 'ORG-AGENCY-STD',
            'AGEN_EXP': 'ORG-AGENCY-STD',
            'DOC_EXP': 'ORG-DOC-EXP',
            'DOC_ORG': 'ORG-DOC-EXP',
            'CUST_EXP': 'ORG-DOC-EXP',
            'CTO': 'ORG-CTO-FEE',
            'CTC_ORG': 'ORG-CTO-FEE',
            
            # Freight components
            'FRT_AIR': 'FRT-AIR-BASE',
            'DOC_AIR': 'FRT-AIR-BASE',  # Treating as part of air freight
            'FUEL_SUR': 'FRT-AIR-FUEL',
            
            # Destination components
            'CARTAGE': 'DST-DELIV-STD',
            'CARTAGE_PERKG': 'DST-DELIV-STD',
            'CARTAGE_MIN': 'DST-DELIV-STD',
            'CARTAGE_FUEL': 'DST-DELIV-FUEL',
            'CLEARANCE': 'DST-CLEAR-CUS',
            'AGENCY_IMP': 'DST-AGENCY-IMP',
            'DOC_IMP': 'DST-DOC-IMP',
            'HANDLING': 'DST-HANDL-STD',
            'HAND_ORG': 'DST-HANDL-STD',  # Assuming destination based on recent fix
            'TERM_INT': 'DST-TERM-INTL',
        }
        
        mapped_count = 0
        unmapped_count = 0
        unmapped_components = []
        
        # Get all service components
        components = ServiceComponent.objects.all()
        
        for component in components:
            service_code_str = COMPONENT_TO_SERVICE_CODE.get(component.code)
            
            if service_code_str:
                try:
                    service_code = ServiceCode.objects.get(code=service_code_str)
                    component.service_code = service_code
                    component.save(update_fields=['service_code'])
                    mapped_count += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ Mapped {component.code} → {service_code_str}'))
                except ServiceCode.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'! Service code {service_code_str} not found for {component.code}'))
                    unmapped_count += 1
                    unmapped_components.append(component.code)
            else:
                self.stdout.write(self.style.WARNING(f'  No mapping for {component.code}'))
                unmapped_count += 1
                unmapped_components.append(component.code)
        
        # Summary
        self.stdout.write(f'\n--- Mapping Summary ---')
        self.stdout.write(self.style.SUCCESS(f'✅ Mapped: {mapped_count} components'))
        
        if unmapped_count > 0:
            self.stdout.write(self.style.WARNING(f'⚠️  Unmapped: {unmapped_count} components'))
            self.stdout.write(f'Unmapped components: {", ".join(unmapped_components)}')
        
        # Verification
        total_components = ServiceComponent.objects.count()
        mapped_total = ServiceComponent.objects.filter(service_code__isnull=False).count()
        unmapped_total = ServiceComponent.objects.filter(service_code__isnull=True).count()
        
        self.stdout.write(f'\n--- Verification ---')
        self.stdout.write(f'Total components: {total_components}')
        self.stdout.write(f'With service_code: {mapped_total}')
        self.stdout.write(f'Without service_code: {unmapped_total}')
        
        if unmapped_total == 0:
            self.stdout.write(self.style.SUCCESS('\n✅ All components mapped successfully!'))
        else:
            self.stdout.write(self.style.WARNING(f'\n⚠️  {unmapped_total} components still need mapping'))
