from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ImportCOGS, Agent

class Command(BaseCommand):
    help = 'Seeds Import COGS (Buy Rates) for BNE/SYD -> POM (EFM AU Only)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Import COGS (EFM AU Rates)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Create Agent
            efm_au, _ = Agent.objects.get_or_create(
                code='EFM-AU',
                defaults={
                    'name': 'EFM Australia',
                    'country_code': 'AU',
                    'agent_type': 'ORIGIN'
                }
            )

            # ORIGIN CHARGES (AUD) - BNE->POM & SYD->POM
            # Rates from User Image: "EFM AU from BNE to POM Import Rates - Door to Airport Only"
            
            origins = ['BNE', 'SYD']
            for org in origins:
                self.stdout.write(f"\nProcessing Origin {org}...")
                
                # --- IMP-FRT-AIR (AUD) ---
                # Min: 330.00
                # +45: 7.05, +100: 6.75, +250: 6.55, +500: 6.25, +1000: 5.95
                frt_wb = [
                    {"min_kg": 45, "rate": "7.05"},
                    {"min_kg": 100, "rate": "6.75"},
                    {"min_kg": 250, "rate": "6.55"},
                    {"min_kg": 500, "rate": "6.25"},
                    {"min_kg": 1000, "rate": "5.95"},
                ]
                
                self._seed_cogs(
                    code='IMP-FRT-AIR', org=org, dest='POM', agent=efm_au, curr='AUD',
                    min_charge='330.00', weight_breaks=frt_wb
                )

                # --- IMP-PICKUP (AUD) ---
                # Min 85.00, 0.26/kg
                self._seed_cogs(
                    code='IMP-PICKUP', org=org, dest='POM', agent=efm_au, curr='AUD',
                    min_charge='85.00', per_kg='0.26'
                )

                # --- IMP-FSC-PICKUP (PERCENT) ---
                # 20%
                self._seed_cogs(
                    code='IMP-FSC-PICKUP', org=org, dest='POM', agent=efm_au, curr='AUD',
                    percent_rate='20.00'
                )

                # --- IMP-SCREEN-ORIGIN (AUD) ---
                # Min 70.00, 0.36/kg
                self._seed_cogs(
                    code='IMP-SCREEN-ORIGIN', org=org, dest='POM', agent=efm_au, curr='AUD',
                    min_charge='70.00', per_kg='0.36'
                )

                # --- IMP-CTO-ORIGIN (AUD) ---
                # Min 30.00, 0.30/kg
                self._seed_cogs(
                    code='IMP-CTO-ORIGIN', org=org, dest='POM', agent=efm_au, curr='AUD',
                    min_charge='30.00', per_kg='0.30'
                )

                # --- IMP-DOC-ORIGIN (AUD) ---
                # Flat 80.00
                self._seed_cogs(
                    code='IMP-DOC-ORIGIN', org=org, dest='POM', agent=efm_au, curr='AUD',
                    flat='80.00'
                )
                
                # --- IMP-AGENCY-ORIGIN (AUD) ---
                # Flat 175.00
                self._seed_cogs(
                    code='IMP-AGENCY-ORIGIN', org=org, dest='POM', agent=efm_au, curr='AUD',
                    flat='175.00'
                )
                
                # --- IMP-AWB-ORIGIN (AUD) ---
                # Flat 25.00
                self._seed_cogs(
                    code='IMP-AWB-ORIGIN', org=org, dest='POM', agent=efm_au, curr='AUD',
                    flat='25.00'
                )


    def _seed_cogs(self, code, org, dest, agent, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import COGS only.
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
                'valid_until': date(2025, 12, 31)
            }
        )
        self.stdout.write(f"  - Seeded COGS {code} {org}->{dest} ({curr})")
