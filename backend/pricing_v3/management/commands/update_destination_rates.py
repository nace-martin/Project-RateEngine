from django.core.management.base import BaseCommand
from decimal import Decimal
from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent

class Command(BaseCommand):
    help = 'Update destination sell rates to correct values'

    def handle(self, *args, **options):
        # Get the BNE->POM lane
        lane = PartnerRateLane.objects.filter(
            origin_airport__iata_code='BNE',
            destination_airport__iata_code='POM',
            mode='AIR',
            shipment_type='IMPORT'
        ).first()

        if not lane:
            self.stdout.write(self.style.ERROR('BNE->POM lane not found!'))
            return

        # Correct destination sell rates from the user's spreadsheet
        correct_rates = [
            {'code': 'CLEARANCE', 'rate': Decimal('300.00')},
            {'code': 'AGENCY_IMP', 'rate': Decimal('250.00')},
            {'code': 'DOC_IMP', 'rate': Decimal('165.00')},
            {'code': 'HANDLING', 'rate': Decimal('165.00')},
            {'code': 'TERM_INT', 'rate': Decimal('165.00')},
            {'code': 'CARTAGE', 'rate': Decimal('1.50'), 'min_charge': Decimal('95.00'), 'is_per_kg': True},
            # Note: CARTAGE_FUEL is 10% of CARTAGE, handled separately
        ]

        updated_count = 0
        for rate_data in correct_rates:
            component = ServiceComponent.objects.filter(code=rate_data['code']).first()
            if not component:
                self.stdout.write(self.style.WARNING(f"Component {rate_data['code']} not found"))
                continue

            # Find existing rate
            partner_rate = PartnerRate.objects.filter(
                lane=lane,
                service_component=component
            ).first()

            if partner_rate:
                # Update the rate
                if rate_data.get('is_per_kg'):
                    partner_rate.rate_per_kg_fcy = rate_data['rate']
                    partner_rate.min_charge_fcy = rate_data.get('min_charge', rate_data['rate'])
                    partner_rate.unit = 'PER_KG'
                else:
                    partner_rate.rate_per_shipment_fcy = rate_data['rate']
                    partner_rate.min_charge_fcy = rate_data['rate']
                    partner_rate.unit = 'SHIPMENT'
                
                partner_rate.save()
                self.stdout.write(self.style.SUCCESS(f"✓ Updated {rate_data['code']}: {rate_data['rate']}"))
                updated_count += 1
            else:
                self.stdout.write(self.style.WARNING(f"No rate found for {rate_data['code']}"))

        self.stdout.write(self.style.SUCCESS(f'\nUpdated {updated_count} destination sell rates'))
