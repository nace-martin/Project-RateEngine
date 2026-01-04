from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ImportCOGS, Agent

class Command(BaseCommand):
    help = 'Seeds Import Destination COGS (EFM-PG A2D) for BNE/SYD -> POM'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import Destination COGS (EFM-PG)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Create/Get Agent
            efm_pg, _ = Agent.objects.get_or_create(
                code='EFM-PG',
                defaults={
                    'name': 'EFM PNG',
                    'country_code': 'PG',
                    'agent_type': 'DESTINATION'
                }
            )

            # We seed for these origins to POM
            origins = ['BNE', 'SYD']
            destination = 'POM'
            
            for org in origins:
                self.stdout.write(f"\nProcessing Origin {org} -> {destination}...")
                
                # 1. Customs Clearance - PGK -
                self._seed_cogs(
                    code='IMP-CLEAR', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    flat='0.00'
                )

                # 2. Agency Fee - PGK -
                self._seed_cogs(
                    code='IMP-AGENCY-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    flat='0.00'
                )

                # 3. Documentation Fee - PGK 50.00
                self._seed_cogs(
                    code='IMP-DOC-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    flat='50.00'
                )

                # 4. Handling Fee - Min PGK 50.00, PGK 0.05/kg
                self._seed_cogs(
                    code='IMP-HANDLING-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    min_charge='50.00', per_kg='0.05'
                )

                # 5. Loading Fee (Forklift) - PGK 50.00
                self._seed_cogs(
                    code='IMP-LOADING-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    flat='50.00'
                )

                # 6. Cartage & Delivery - PGK -
                self._seed_cogs(
                    code='IMP-CARTAGE-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    flat='0.00', per_kg='0.00' 
                )

                # 7. Fuel Surcharge - Cartage 10% -> COGS is 0%?
                # Image has '%' column but empty for FSC? No, wait.
                # Image says "Fuel Surcharge - Cartage 10%".
                # But under COGS/BUY RATES, the row for FSC has empty values for Flat, Min, Per Kg, Max, %.
                # Actually, the last column '%' is empty. 
                # So the cost is 0?
                # "Import Clearance and Delivery (A2D) COGS/BUY RATES"
                # Row "Fuel Surcharge - Cartage 10%" -> visual placeholder?
                # Values are empty. I will assume 0.00 cost.
                
                self._seed_cogs(
                    code='IMP-FSC-CARTAGE-DEST', org=org, dest=destination, agent=efm_pg, curr='PGK',
                    percent_rate='0.00'
                )

    def _seed_cogs(self, code, org, dest, agent, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import COGS.
        """
        try:
            pc = ProductCode.objects.get(code=code)
        except ProductCode.DoesNotExist:
            self.stdout.write(f"  ! Error: ProductCode {code} not found")
            return

        ImportCOGS.objects.update_or_create(
            product_code=pc, origin_airport=org, destination_airport=dest,
            agent=agent, valid_from=date(2025, 1, 1),
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
        self.stdout.write(f"  - Seeded COGS {code} {org}->{dest} ({curr})")
