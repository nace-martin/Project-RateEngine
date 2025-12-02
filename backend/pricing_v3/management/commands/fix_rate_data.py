from django.core.management.base import BaseCommand
from services.models import ServiceComponent
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fixes service component data for pricing engine v3'

    def handle(self, *args, **options):
        # 1. Set Destination charges to RATE_OFFER (Pass-through)
        dest_codes = [
            'CLEARANCE', 'AGENCY_IMP', 'DOC_IMP', 'HANDLING', 
            'TERM_INT', 'CARTAGE', 'CARTAGE_FUEL', 'XRAY'
        ]
        
        updated = ServiceComponent.objects.filter(
            code__in=dest_codes
        ).update(cost_type='RATE_OFFER', leg='DESTINATION')
        
        self.stdout.write(self.style.SUCCESS(f'Updated {updated} destination components to RATE_OFFER'))

        # 2. Set Origin charges to COGS (Buy-rates)
        origin_codes = [
            'PICKUP', 'PICKUP_FUEL', 'AWB_FEE', 'FRT_AIR', 
            'DOC_EXP', 'AGENCY_EXP', 'CTO'
        ]
        
        updated = ServiceComponent.objects.filter(
            code__in=origin_codes
        ).update(cost_type='COGS', leg='ORIGIN')
        
        self.stdout.write(self.style.SUCCESS(f'Updated {updated} origin components to COGS'))

        # 3. Configure Fuel Surcharge
        try:
            cartage = ServiceComponent.objects.get(code='CARTAGE')
            fuel = ServiceComponent.objects.get(code='CARTAGE_FUEL')
            
            fuel.percent_of_component = cartage
            fuel.percent_value = Decimal('10.00')
            fuel.save()
            
            self.stdout.write(self.style.SUCCESS('Configured CARTAGE_FUEL as 10% of CARTAGE'))
        except ServiceComponent.DoesNotExist:
            self.stdout.write(self.style.WARNING('Could not configure fuel surcharge - components missing'))
