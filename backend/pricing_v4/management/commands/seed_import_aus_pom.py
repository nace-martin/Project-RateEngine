from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, ImportCOGS, Agent, Carrier

class Command(BaseCommand):
    help = 'Seeds Import COGS (Buy Rates) for BNE/SYD -> POM'

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
            px, _ = Carrier.objects.get_or_create(
                code='PX',
                defaults={
                    'name': 'Air Niugini',
                    'carrier_type': 'AIRLINE',
                },
            )

            freight_cards = {
                'BNE': {
                    'min_charge': '350.00',
                    'weight_breaks': [
                        {"min_kg": 0, "rate": "7.50"},
                        {"min_kg": 45, "rate": "7.35"},
                        {"min_kg": 100, "rate": "7.00"},
                        {"min_kg": 250, "rate": "6.75"},
                        {"min_kg": 500, "rate": "6.45"},
                        {"min_kg": 1000, "rate": "6.10"},
                    ],
                },
                'SYD': {
                    'min_charge': '415.00',
                    'weight_breaks': [
                        {"min_kg": 45, "rate": "8.10"},
                        {"min_kg": 100, "rate": "7.55"},
                        {"min_kg": 250, "rate": "7.50"},
                        {"min_kg": 500, "rate": "7.20"},
                        {"min_kg": 1000, "rate": "6.85"},
                    ],
                },
            }

            for org, freight_card in freight_cards.items():
                self.stdout.write(f"\nProcessing Origin {org}...")

                self._seed_cogs(
                    code='IMP-FRT-AIR',
                    org=org,
                    dest='POM',
                    agent=None,
                    carrier=px,
                    scope='LANE',
                    curr='AUD',
                    min_charge=freight_card['min_charge'],
                    weight_breaks=freight_card['weight_breaks'],
                )

                # Origin-local import COGS are origin-scoped, not BNE/SYD -> POM lane rows.
                self._seed_cogs(
                    code='IMP-PICKUP', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', min_charge='85.00', per_kg='0.26'
                )

                self._seed_cogs(
                    code='IMP-FSC-PICKUP', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', percent_rate='20.00'
                )

                self._seed_cogs(
                    code='IMP-SCREEN-ORIGIN', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', min_charge='70.00', per_kg='0.382'
                )

                self._seed_cogs(
                    code='IMP-CTO-ORIGIN', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', flat='30.00'
                )

                self._seed_cogs(
                    code='IMP-DOC-ORIGIN', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', flat='82.00'
                )
                
                self._seed_cogs(
                    code='IMP-AGENCY-ORIGIN', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD',
                    flat='175.00'
                )
                
                self._seed_cogs(
                    code='IMP-AWB-ORIGIN', org=org, dest=None, agent=efm_au, carrier=None, scope='ORIGIN',
                    curr='AUD', flat='30.00'
                )


    def _seed_cogs(self, code, org, dest, agent, carrier, scope, curr,
                   flat=None, per_kg=None, min_charge=None, max_charge=None, weight_breaks=None, percent_rate=None):
        """
        Seeds Import COGS only.
        """
        try:
            pc = ProductCode.objects.get(code=code)
        except ProductCode.DoesNotExist:
            self.stdout.write(f"  ! Error: ProductCode {code} not found")
            return

        seed_values = {
            'rate_per_shipment': Decimal(flat) if flat else None,
            'rate_per_kg': Decimal(per_kg) if per_kg else None,
            'min_charge': Decimal(min_charge) if min_charge else None,
            'max_charge': Decimal(max_charge) if max_charge else None,
            'weight_breaks': weight_breaks,
            'percent_rate': Decimal(percent_rate) if percent_rate else None,
            'is_additive': False,
            'scope': scope,
        }
        lookup = {
            'product_code': pc,
            'origin_airport': org,
            'agent': agent,
            'carrier': carrier,
            'currency': curr,
            'valid_from': date(2025, 1, 1),
            'valid_until': date(2026, 12, 31),
        }
        if code == 'IMP-FRT-AIR':
            matches = ImportCOGS.objects.filter(
                product_code=pc,
                origin_airport=org,
                destination_airport=dest,
                currency=curr,
                valid_from=date(2025, 1, 1),
                valid_until=date(2026, 12, 31),
            ).order_by('id')
        elif dest is None:
            matches = ImportCOGS.objects.filter(**lookup).order_by('id')
        else:
            matches = ImportCOGS.objects.filter(**lookup, destination_airport=dest).order_by('id')

        if matches.exists():
            if matches.count() > 1:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ! Duplicate ImportCOGS rows found for {code} {org}->{dest} ({curr}); updating all matches"
                    )
                )
            for obj in matches:
                obj.destination_airport = dest
                for field, value in seed_values.items():
                    setattr(obj, field, value)
                obj.save()
        else:
            obj = ImportCOGS(**lookup, destination_airport=dest)
            for field, value in seed_values.items():
                setattr(obj, field, value)
            obj.save()
        self.stdout.write(f"  - Seeded COGS {code} {org}->{dest} ({curr})")
