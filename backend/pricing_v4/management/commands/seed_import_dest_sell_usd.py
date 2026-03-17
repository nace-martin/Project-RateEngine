from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode
from pricing_v4.management.commands._sell_seed_utils import seed_import_sell_rate

class Command(BaseCommand):
    help = 'Seeds Import Destination Sell Rates in USD for Prepaid Import (Non-Australian Origins)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import Destination Sell Rates (USD)")
        self.stdout.write("For Prepaid Import from Non-Australian Origins")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Common international origin airports (non-Australian)
            # This covers major hubs that ship to POM
            origins = [
                'LAX', 'SFO', 'JFK',  # USA
                'SIN', 'HKG', 'NRT',  # Asia
                'AKL',                # New Zealand
                'DXB', 'LHR'          # Middle East / Europe
            ]
            destination = 'POM'
            
            for org in origins:
                self.stdout.write(f"\nProcessing Origin {org} -> {destination}...")
                
                # 1. Customs Clearance - Flat USD 105.00
                self._seed_sell(
                    code='IMP-CLEAR', org=org, dest=destination, curr='USD',
                    flat='105.00'
                )

                # 2. Agency Fee - Flat USD 90.00
                self._seed_sell(
                    code='IMP-AGENCY-DEST', org=org, dest=destination, curr='USD',
                    flat='90.00'
                )

                # 3. Documentation Fee - Flat USD 60.00
                self._seed_sell(
                    code='IMP-DOC-DEST', org=org, dest=destination, curr='USD',
                    flat='60.00'
                )

                # 4. Handling Fee - Flat USD 60.00
                self._seed_sell(
                    code='IMP-HANDLING-DEST', org=org, dest=destination, curr='USD',
                    flat='60.00'
                )

                # 5. Cartage & Delivery - USD 0.55/kg, Min 40.00, Max 500.00
                self._seed_sell(
                    code='IMP-CARTAGE-DEST', org=org, dest=destination, curr='USD',
                    min_charge='40.00', per_kg='0.55', max_charge='500.00'
                )

                # 6. Fuel Surcharge - Cartage 10%
                self._seed_sell(
                    code='IMP-FSC-CARTAGE-DEST', org=org, dest=destination, curr='USD',
                    percent_rate='10.00'
                )

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully seeded USD sell rates for {len(origins)} origins"))

    def _seed_sell(self, code, org, dest, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import Sell Rate in USD.
        """
        try:
            pc = ProductCode.objects.get(code=code)
        except ProductCode.DoesNotExist:
            self.stdout.write(f"  ! Error: ProductCode {code} not found")
            return

        percent_of_pc = None
        if percent_rate:
            percent_of_pc = ProductCode.objects.get(code='IMP-CARTAGE-DEST')

        result = seed_import_sell_rate(
            product_code=pc,
            origin_airport=org,
            destination_airport=dest,
            currency=curr,
            valid_from=date(2025, 1, 1),
            valid_until=date(2026, 12, 31),
            rate_per_shipment=Decimal(flat) if flat else None,
            rate_per_kg=Decimal(per_kg) if per_kg else None,
            min_charge=Decimal(min_charge) if min_charge else None,
            max_charge=Decimal(max_charge) if max_charge else None,
            weight_breaks=weight_breaks,
            percent_rate=Decimal(percent_rate) if percent_rate else None,
            payment_term='PREPAID',
            percent_of_product_code=percent_of_pc,
        )
        self.stdout.write(f"  - Seeded {result.table_name} {code} {org}->{dest} ({curr})")
