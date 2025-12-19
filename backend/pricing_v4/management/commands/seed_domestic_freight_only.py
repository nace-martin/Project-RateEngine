from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date
from pricing_v4.models import ProductCode, DomesticCOGS, Carrier

class Command(BaseCommand):
    help = 'Seeds Domestic COGS for ex-POM routes (FREIGHT ONLY - normalized design)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Domestic COGS (ex-POM) - FREIGHT ONLY (Carrier PX)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # Get or create Carrier for Air Niugini
            px_carrier, _ = Carrier.objects.get_or_create(
                code='PX',
                defaults={
                    'name': 'Air Niugini',
                    'carrier_type': 'AIRLINE'
                }
            )

            origin = 'POM'
            
            # Ex-POM Air Freight Rates (PGK per kg) - ONLY FREIGHT, NO SURCHARGES
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

            # Seed Freight COGS ONLY for each destination
            frt_pc = ProductCode.objects.get(code='DOM-FRT-AIR')
            
            for dest, rate in freight_rates.items():
                DomesticCOGS.objects.update_or_create(
                    product_code=frt_pc,
                    origin_zone=origin,
                    destination_zone=dest,
                    carrier=px_carrier,
                    valid_from=date(2025, 1, 1),
                    defaults={
                        'agent': None,
                        'currency': 'PGK',
                        'rate_per_kg': Decimal(rate),
                        'valid_until': date(2025, 12, 31)
                    }
                )
                self.stdout.write(f"  - Seeded FREIGHT {origin}->{dest}: K{rate}/kg")

        self.stdout.write(f"\nSeeded {len(freight_rates)} freight-only routes (normalized design)")
        self.stdout.write("Surcharges are stored globally in Surcharge table")
