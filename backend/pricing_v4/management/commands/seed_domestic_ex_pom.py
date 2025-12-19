from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, DomesticCOGS, Agent

class Command(BaseCommand):
    help = 'Seeds Domestic COGS for ex-POM routes (Air Niugini rates)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Domestic COGS (ex-POM routes)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Get or create Agent for Air Niugini (domestic uses Agent, not Carrier)
            px_agent, _ = Agent.objects.get_or_create(
                code='PX-DOM',
                defaults={
                    'name': 'Air Niugini (Domestic)',
                    'agent_type': 'CARRIER',
                    'country_code': 'PG'
                }
            )

            origin = 'POM'
            
            # Ex-POM Air Freight Rates (PGK per kg)
            freight_rates = {
                'GUR': '7.85',
                'BUA': '19.35',
                'DAU': '11.05',
                'GKA': '8.30',
                'HKN': '11.55',
                'KVG': '17.65',
                'KIE': '20.45',
                'KOM': '14.00',
                'UNG': '16.05',
                'CMU': '7.20',
                'LAE': '6.10',
                'LNV': '18.75',
                'LSA': '8.00',
                'MAG': '8.75',
                'MAS': '13.25',
                'MDU': '9.50',
                'HGU': '8.85',
                'PNP': '4.85',
                'RAB': '15.45',
                'TBG': '16.05',
                'TIZ': '14.00',
                'TFI': '5.25',
                'VAI': '17.15',
                'WBM': '6.65',
                'WWK': '13.75',
            }

            # Seed Freight COGS for each destination
            frt_pc = ProductCode.objects.get(code='DOM-FRT-AIR')
            
            for dest, rate in freight_rates.items():
                self._seed_cogs(
                    pc=frt_pc, 
                    origin=origin, 
                    dest=dest, 
                    agent=px_agent,
                    per_kg=rate
                )
            
            # Additional Charges (apply to all routes)
            self.stdout.write("\nSeeding Additional Charges...")
            
            # Documentation Fee: PGK 35.00 flat
            doc_pc = ProductCode.objects.get(code='DOM-DOC')
            for dest in freight_rates.keys():
                self._seed_cogs(pc=doc_pc, origin=origin, dest=dest, agent=px_agent, flat='35.00')
            
            # Terminal Fee: PGK 35.00 flat
            term_pc = ProductCode.objects.get(code='DOM-TERMINAL')
            for dest in freight_rates.keys():
                self._seed_cogs(pc=term_pc, origin=origin, dest=dest, agent=px_agent, flat='35.00')
            
            # Security Surcharge: Min PGK 5.00 or 0.20 per kg
            sec_pc = ProductCode.objects.get(code='DOM-SECURITY')
            for dest in freight_rates.keys():
                self._seed_cogs(pc=sec_pc, origin=origin, dest=dest, agent=px_agent, per_kg='0.20', min_charge='5.00')
            
            # Fuel Surcharge: PGK 0.25 per kg
            fsc_pc = ProductCode.objects.get(code='DOM-FSC')
            for dest in freight_rates.keys():
                self._seed_cogs(pc=fsc_pc, origin=origin, dest=dest, agent=px_agent, per_kg='0.25')

        self.stdout.write(f"\nSeeded {len(freight_rates)} destinations with freight + ancillaries")

    def _seed_cogs(self, pc, origin, dest, agent,
                   flat=None, per_kg=None, min_charge=None, max_charge=None):
        """Seeds Domestic COGS record using zone fields."""
        DomesticCOGS.objects.update_or_create(
            product_code=pc,
            origin_zone=origin,  # Uses zone, not airport
            destination_zone=dest,  # Uses zone, not airport
            agent=agent,  # Uses agent, not carrier
            valid_from=date(2025, 1, 1),
            defaults={
                'currency': 'PGK',
                'rate_per_shipment': Decimal(flat) if flat else None,
                'rate_per_kg': Decimal(per_kg) if per_kg else None,
                'min_charge': Decimal(min_charge) if min_charge else None,
                'max_charge': Decimal(max_charge) if max_charge else None,
                'valid_until': date(2025, 12, 31)
            }
        )
        self.stdout.write(f"  - Seeded COGS {pc.code} {origin}->{dest}")
