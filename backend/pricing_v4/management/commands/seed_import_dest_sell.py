from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ImportSellRate

class Command(BaseCommand):
    help = 'Seeds Import Destination Sell Rates (EFM-PG A2D) for BNE/SYD -> POM'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import Destination Sell Rates (EFM-PG)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # We seed for these origins to POM
            origins = ['BNE', 'SYD']
            destination = 'POM'
            
            for org in origins:
                self.stdout.write(f"\nProcessing Origin {org} -> {destination}...")
                
                # 1. Customs Clearance - Flat K300.00
                self._seed_sell(
                    code='IMP-CLEAR', org=org, dest=destination, curr='PGK',
                    flat='300.00'
                )

                # 2. Agency Fee - Flat K300.00
                self._seed_sell(
                    code='IMP-AGENCY-DEST', org=org, dest=destination, curr='PGK',
                    flat='300.00'
                )

                # 3. Documentation Fee - Flat K150.00
                self._seed_sell(
                    code='IMP-DOC-DEST', org=org, dest=destination, curr='PGK',
                    flat='150.00'
                )

                # 4. Handling Fee - Min K150.00, K1.50/kg
                self._seed_sell(
                    code='IMP-HANDLING-DEST', org=org, dest=destination, curr='PGK',
                    min_charge='150.00', per_kg='1.50'
                )

                # 5. Loading Fee (Forklift) - Flat K150.00
                self._seed_sell(
                    code='IMP-LOADING-DEST', org=org, dest=destination, curr='PGK',
                    flat='150.00'
                )

                # 6. Cartage & Delivery - Min K95.00, K1.50/kg, Max K500.00
                self._seed_sell(
                    code='IMP-CARTAGE-DEST', org=org, dest=destination, curr='PGK',
                    min_charge='95.00', per_kg='1.50', max_charge='500.00'
                )

                # 7. Fuel Surcharge - Cartage 10%
                self._seed_sell(
                    code='IMP-FSC-CARTAGE-DEST', org=org, dest=destination, curr='PGK',
                    percent_rate='10.00'
                )

    def _seed_sell(self, code, org, dest, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import Sell Rate.
        """
        try:
            pc = ProductCode.objects.get(code=code)
        except ProductCode.DoesNotExist:
            self.stdout.write(f"  ! Error: ProductCode {code} not found")
            return

        ImportSellRate.objects.update_or_create(
            product_code=pc, origin_airport=org, destination_airport=dest,
            valid_from=date(2025, 1, 1),
            defaults={
                'currency': curr,
                'rate_per_shipment': Decimal(flat) if flat else None,
                'rate_per_kg': Decimal(per_kg) if per_kg else None,
                'min_charge': Decimal(min_charge) if min_charge else None,
                'max_charge': Decimal(max_charge) if max_charge else None,
                'weight_breaks': weight_breaks,
                'percent_rate': Decimal(percent_rate) if percent_rate else None,
                'valid_until': date(2026, 12, 31)
            }
        )
        self.stdout.write(f"  - Seeded Sell Rate {code} {org}->{dest} ({curr})")
