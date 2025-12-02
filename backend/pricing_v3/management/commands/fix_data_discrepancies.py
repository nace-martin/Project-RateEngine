from django.core.management.base import BaseCommand
from ratecards.models import PartnerRate
from services.models import ServiceComponent
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fix data discrepancies for PICKUP, XRAY, and PICKUP_FUEL'

    def handle(self, *args, **options):
        # 1. Fix PICKUP PartnerRate
        # Assuming BNE->POM lane exists and is the one we are testing
        pickup_rates = PartnerRate.objects.filter(
            service_component__code='PICKUP',
            lane__origin_airport__iata_code='BNE',
            lane__destination_airport__iata_code='POM'
        )
        for rate in pickup_rates:
            rate.min_charge_fcy = Decimal('85.00')
            rate.rate_per_kg_fcy = Decimal('0.26')
            rate.unit = 'PER_KG' # Ensure unit is correct
            rate.save()
            self.stdout.write(self.style.SUCCESS(f"Updated PICKUP rate: Min 85.00, Rate 0.26"))

        # 2. Fix XRAY PartnerRate and Component
        xray_rates = PartnerRate.objects.filter(
            service_component__code='XRAY',
            lane__origin_airport__iata_code='BNE',
            lane__destination_airport__iata_code='POM'
        )
        for rate in xray_rates:
            rate.min_charge_fcy = Decimal('70.00')
            rate.rate_per_kg_fcy = Decimal('0.36')
            rate.unit = 'PER_KG'
            rate.save()
            self.stdout.write(self.style.SUCCESS(f"Updated XRAY rate: Min 70.00, Rate 0.36"))
        
        # Fix XRAY Component cost_type
        xray_comp = ServiceComponent.objects.get(code='XRAY')
        if xray_comp.cost_type == 'RATE_OFFER':
            xray_comp.cost_type = 'COGS'
            xray_comp.save()
            self.stdout.write(self.style.SUCCESS(f"Updated XRAY component cost_type to COGS"))

        # 3. Fix PICKUP_FUEL Component
        pickup_comp = ServiceComponent.objects.get(code='PICKUP')
        fuel_comp = ServiceComponent.objects.get(code='PICKUP_FUEL')
        
        fuel_comp.percent_of_component = pickup_comp
        fuel_comp.percent_value = Decimal('20.0')
        fuel_comp.save()
        self.stdout.write(self.style.SUCCESS(f"Updated PICKUP_FUEL: 20% of PICKUP"))
