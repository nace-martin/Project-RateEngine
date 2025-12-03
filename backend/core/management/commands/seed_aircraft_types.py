# backend/core/management/commands/seed_aircraft_types.py

from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import AircraftType


class Command(BaseCommand):
    help = 'Seed aircraft types with cargo door constraints'

    def handle(self, *args, **options):
        self.stdout.write("Seeding aircraft types...")
        
        # B737 - Narrow-Body (Direct SYD→POM)
        b737, created = AircraftType.objects.update_or_create(
            code='B737',
            defaults={
                'name': 'Boeing 737 (Narrow-Body)',
                'aircraft_class': AircraftType.AircraftClass.NARROW_BODY,
                'max_length_cm': Decimal('200.00'),
                'max_width_cm': Decimal('120.00'),
                'max_height_cm': Decimal('85.00'),  # FWD door (AFT is 80cm, using more restrictive)
                'max_piece_weight_kg': Decimal('250.00'),
                'supports_uld': False,
                'notes': 'Standard narrow-body cargo door. Operated by Air Niugini and Qantas on SYD-POM direct route.'
            }
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} {b737}")
        )
        
        # B767 - Wide-Body (Via BNE route)
        b767, created = AircraftType.objects.update_or_create(
            code='B767',
            defaults={
                'name': 'Boeing 767 (Wide-Body)',
                'aircraft_class': AircraftType.AircraftClass.WIDE_BODY,
                'max_length_cm': Decimal('317.50'),  # PMC Container length
                'max_width_cm': Decimal('243.80'),  # PMC Container width
                'max_height_cm': Decimal('162.60'),  # PMC Container height
                'max_piece_weight_kg': Decimal('2000.00'),  # Generous for ULD capacity
                'supports_uld': True,
                'notes': 'Wide-body aircraft with ULD capability. Supports PMC (317.5×243.8×162.6cm) and DQF (LD-8) containers. Operated by Air Niugini on BNE-POM route.'
            }
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} {b767}")
        )
        
        self.stdout.write(
            self.style.SUCCESS("\nAircraft types seeded successfully!")
        )
