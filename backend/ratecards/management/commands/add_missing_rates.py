from django.core.management.base import BaseCommand
from decimal import Decimal
from ratecards.models import PartnerRateLane, PartnerRate
from services.models import ServiceComponent

class Command(BaseCommand):
    help = 'Add missing component rates to BNE->POM lane'

    def handle(self, *args, **options):
        # Get the lane
        lane = PartnerRateLane.objects.filter(
            origin_airport__iata_code='BNE',
            destination_airport__iata_code='POM',
            mode='AIR',
            shipment_type='IMPORT'
        ).first()

        if not lane:
            self.stdout.write(self.style.ERROR('BNE->POM lane not found!'))
            return

        self.stdout.write(f'Found lane: {lane}')

        # Define the missing rates we need to add
        missing_rates = [
            {'code': 'AGENCY_IMP', 'rate': Decimal('75.00'), 'min_charge': Decimal('75.00'), 'unit': 'FLAT'},
            {'code': 'CARTAGE', 'rate': Decimal('2.50'), 'min_charge': Decimal('150.00'), 'unit': 'PER_KG'},
            {'code': 'CARTAGE_FUEL', 'rate': Decimal('25.00'), 'min_charge': Decimal('25.00'), 'unit': 'FLAT'},
            {'code': 'CLEARANCE', 'rate': Decimal('120.00'), 'min_charge': Decimal('120.00'), 'unit': 'FLAT'},
            {'code': 'DOC_IMP', 'rate': Decimal('45.00'), 'min_charge': Decimal('45.00'), 'unit': 'FLAT'},
            {'code': 'PICKUP', 'rate': Decimal('95.00'), 'min_charge': Decimal('95.00'), 'unit': 'FLAT'},
            {'code': 'PICKUP_FUEL', 'rate': Decimal('20.00'), 'min_charge': Decimal('20.00'), 'unit': 'FLAT'},
            {'code': 'TERM_INT', 'rate': Decimal('85.00'), 'min_charge': Decimal('85.00'), 'unit': 'FLAT'},
            {'code': 'XRAY', 'rate': Decimal('60.00'), 'min_charge': Decimal('60.00'), 'unit': 'FLAT'},
            {'code': 'FRT_DEST', 'rate': Decimal('0.85'), 'min_charge': Decimal('120.00'), 'unit': 'PER_KG'},
        ]

        created_count = 0
        for rate_data in missing_rates:
            # Get the component
            component = ServiceComponent.objects.filter(code=rate_data['code']).first()
            if not component:
                self.stdout.write(self.style.WARNING(f"Component {rate_data['code']} not found, skipping"))
                continue

            # Check if rate already exists
            existing = PartnerRate.objects.filter(
                lane=lane,
                service_component=component
            ).exists()

            if existing:
                self.stdout.write(f"  Rate for {rate_data['code']} already exists, skipping")
                continue

            # Create the rate
            if rate_data['unit'] == 'PER_KG':
                rate_obj = PartnerRate.objects.create(
                    lane=lane,
                    service_component=component,
                    unit='PER_KG',
                    min_charge_fcy=rate_data['min_charge'],
                    rate_per_kg_fcy=rate_data['rate']
                )
            else:  # SHIPMENT (flat rate)
                rate_obj = PartnerRate.objects.create(
                    lane=lane,
                    service_component=component,
                    unit='SHIPMENT',
                    min_charge_fcy=rate_data['min_charge'],
                    rate_per_shipment_fcy=rate_data['rate']
                )

            self.stdout.write(self.style.SUCCESS(f"  Created rate for {rate_data['code']}"))
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f'\nCreated {created_count} new rates'))
