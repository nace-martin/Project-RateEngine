from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ImportSellRate

class Command(BaseCommand):
    help = 'Seeds Import Destination Sell Rates in AUD for Prepaid Import (Australian Origins)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import Destination Sell Rates (AUD)")
        self.stdout.write("For Prepaid Import from Australian Origins")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Australian origin airports
            origins = ['BNE', 'SYD', 'MEL', 'ADL', 'PER', 'CNS', 'DRW']
            destination = 'POM'
            
            for org in origins:
                self.stdout.write(f"\nProcessing Origin {org} -> {destination}...")
                
                # 1. Customs Clearance - Flat AUD 145.00
                self._seed_sell(
                    code='IMP-CLEAR', org=org, dest=destination, curr='AUD',
                    flat='145.00'
                )

                # 2. Agency Fee - Flat AUD 120.00
                self._seed_sell(
                    code='IMP-AGENCY-DEST', org=org, dest=destination, curr='AUD',
                    flat='120.00'
                )

                # 3. Documentation Fee - Flat AUD 80.00
                self._seed_sell(
                    code='IMP-DOC-DEST', org=org, dest=destination, curr='AUD',
                    flat='80.00'
                )

                # 4. Handling Fee - Flat AUD 80.00
                self._seed_sell(
                    code='IMP-HANDLING-DEST', org=org, dest=destination, curr='AUD',
                    flat='80.00'
                )

                # 5. Cartage & Delivery - AUD 0.75/kg, Min 50.00, Max 500.00
                self._seed_sell(
                    code='IMP-CARTAGE-DEST', org=org, dest=destination, curr='AUD',
                    min_charge='50.00', per_kg='0.75', max_charge='500.00'
                )

                # 6. Fuel Surcharge - Cartage 10%
                self._seed_sell(
                    code='IMP-FSC-CARTAGE-DEST', org=org, dest=destination, curr='AUD',
                    percent_rate='10.00'
                )

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully seeded AUD sell rates for {len(origins)} origins"))

    def _seed_sell(self, code, org, dest, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import Sell Rate in AUD.
        """
        try:
            pc = ProductCode.objects.get(code=code)
        except ProductCode.DoesNotExist:
            self.stdout.write(f"  ! Error: ProductCode {code} not found")
            return

        ImportSellRate.objects.update_or_create(
            product_code=pc, origin_airport=org, destination_airport=dest,
            currency=curr,  # Include currency in unique lookup
            valid_from=date(2025, 1, 1),
            defaults={
                'rate_per_shipment': Decimal(flat) if flat else None,
                'rate_per_kg': Decimal(per_kg) if per_kg else None,
                'min_charge': Decimal(min_charge) if min_charge else None,
                'max_charge': Decimal(max_charge) if max_charge else None,
                'weight_breaks': weight_breaks,
                'percent_rate': Decimal(percent_rate) if percent_rate else None,
                'valid_until': date(2026, 12, 31)
            }
        )
        self.stdout.write(f"  - Seeded {code} {org}->{dest} ({curr})")
