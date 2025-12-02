from django.core.management.base import BaseCommand
from services.models import ServiceComponent

class Command(BaseCommand):
    help = 'Fix leg assignments for all service components'

    def handle(self, *args, **options):
        # Origin components (charged at origin, subject to FX + CAF + Margin)
        origin_codes = [
            'PICKUP', 'PICKUP_FUEL', 'AWB_FEE', 'XRAY', 'AGENCY_EXP', 'DOC_EXP', 'CTO'
        ]
        
        # Main/Freight components
        main_codes = ['FRT_AIR', 'FRT_SEA']
        
        # Destination components (pass-through sell rates)
        dest_codes = [
            'CARTAGE', 'CARTAGE_FUEL', 'CLEARANCE', 'AGENCY_IMP', 'DOC_IMP',
            'HANDLING', 'TERM_INT'  # These are POM destination charges
        ]
        
        updated = 0
        
        # Set ORIGIN leg
        for code in origin_codes:
            result = ServiceComponent.objects.filter(code=code).update(leg='ORIGIN')
            if result:
                self.stdout.write(self.style.SUCCESS(f'✓ Set {code} to ORIGIN'))
                updated += result
        
        # Set MAIN leg
        for code in main_codes:
            result = ServiceComponent.objects.filter(code=code).update(leg='MAIN')
            if result:
                self.stdout.write(self.style.SUCCESS(f'✓ Set {code} to MAIN'))
                updated += result
        
        # Set DESTINATION leg
        for code in dest_codes:
            result = ServiceComponent.objects.filter(code=code).update(leg='DESTINATION')
            if result:
                self.stdout.write(self.style.SUCCESS(f'✓ Set {code} to DESTINATION'))
                updated += result
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Updated {updated} components'))
        
        # Show current status
        self.stdout.write('\n--- Current Leg Assignments ---')
        for comp in ServiceComponent.objects.all().order_by('leg', 'code'):
            leg_display = comp.leg if comp.leg else 'UNSET'
            self.stdout.write(f'{comp.code:20} {leg_display}')
