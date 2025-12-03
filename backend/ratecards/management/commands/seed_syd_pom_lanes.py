# backend/ratecards/management/commands/seed_syd_pom_lanes.py

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Location, AircraftType, RouteLaneConstraint
from parties.models import Company
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent


class Command(BaseCommand):
    help = 'Seed SYD-POM lanes with DIRECT and VIA_BNE rate cards'

    def handle(self, *args, **options):
        self.stdout.write("Setting up SYD-POM routing lanes...")
        
        # Get or create locations
        syd, _ = Location.objects.get_or_create(
            code='SYD',
            defaults={'name': 'SYD - Sydney'}
        )
        pom, _ = Location.objects.get_or_create(
            code='POM',
            defaults={'name': 'POM - Port Moresby'}
        )
        bne, _ = Location.objects.get_or_create(
            code='BNE',
            defaults={'name': 'BNE - Brisbane'}
        )
        
        # Get aircraft types
        try:
            b737 = AircraftType.objects.get(code='B737')
            b767 = AircraftType.objects.get(code='B767')
        except AircraftType.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("Aircraft types not found! Run 'python manage.py seed_aircraft_types' first.")
            )
            return
        
        # Create route lane constraints
        direct_lane, created = RouteLaneConstraint.objects.update_or_create(
            origin=syd,
            destination=pom,
            service_level='DIRECT',
            defaults={
                'aircraft_type': b737,
                'is_active': True,
                'priority': 1,  # Highest priority - try this first
            }
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} DIRECT lane: {direct_lane}")
        )
        
        via_bne_lane, created = RouteLaneConstraint.objects.update_or_create(
            origin=syd,
            destination=pom,
            service_level='VIA_BNE',
            defaults={
                'aircraft_type': b767,
                'via_location': bne,
                'is_active': True,
                'priority': 2,  # Fallback if DIRECT doesn't work
            }
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} VIA_BNE lane: {via_bne_lane}")
        )
        
        # Get or create EFM supplier
        efm, _ = Company.objects.get_or_create(
            name='EFM AU',
            defaults={
                'company_type': 'PARTNER',
                'is_active': True
            }
        )
        
        # Create DIRECT rate card
        self.stdout.write("\nCreating DIRECT rate card...")
        direct_card = self._create_rate_card(
            efm=efm,
            name='EFM AU SYD-POM DIRECT Import 2025',
            service_level='DIRECT',
            route_lane=direct_lane,
            syd=syd,
            pom=pom,
            min_charge=Decimal('330.00'),
            rate_per_kg=Decimal('7.05')
        )
        
        # Create VIA_BNE rate card
        self.stdout.write("\nCreating VIA_BNE rate card...")
        via_card = self._create_rate_card(
            efm=efm,
            name='EFM AU SYD-POM VIA BNE Import 2025',
            service_level='VIA_BNE',
            route_lane=via_bne_lane,
            syd=syd,
            pom=pom,
            min_charge=Decimal('400.00'),
            rate_per_kg=Decimal('7.75')
        )
        
        self.stdout.write(
            self.style.SUCCESS("\nSYD-POM lanes and rate cards seeded successfully!")
        )
    
    def _create_rate_card(self, efm, name, service_level, route_lane, syd, pom, min_charge, rate_per_kg):
        """Helper to create a rate card with rates"""
        
        # Create rate card
        card, created = PartnerRateCard.objects.update_or_create(
            name=name,
            defaults={
                'supplier': efm,
                'currency_code': 'AUD',
                'valid_from': timezone.now().date(),
                'service_level': service_level,
                'route_lane_constraint': route_lane,
            }
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'} rate card: {name}")
        
        # Create lane
        lane, created = PartnerRateLane.objects.update_or_create(
            rate_card=card,
            origin_airport_id=syd.code,
            destination_airport_id=pom.code,
            defaults={
                'mode': 'AIR',
                'shipment_type': 'IMPORT',
            }
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'} lane: SYD->POM")
        
        # Get service components
        try:
            frt_air = ServiceComponent.objects.get(code='FRT_AIR')
            pickup = ServiceComponent.objects.get(code='PICKUP')
            pickup_fuel = ServiceComponent.objects.get(code='PICKUP_FUEL')
            xray = ServiceComponent.objects.get(code='XRAY')
        except ServiceComponent.DoesNotExist as e:
            self.stdout.write(self.style.WARNING(f"  Service component not found: {e}"))
            return card
        
        # Create rates
        rates_data = [
            (frt_air, min_charge, rate_per_kg, 'PER_KG'),
            (pickup, Decimal('85.00'), Decimal('0.26'), 'PER_KG'),
            (xray, Decimal('70.00'), Decimal('0.36'), 'PER_KG'),
        ]
        
        for component, min_chg, rate, unit in rates_data:
            rate_obj, created = PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=component,
                defaults={
                    'unit': unit,
                    'min_charge_fcy': min_chg,
                    'rate_per_kg_fcy': rate,
                }
            )
            self.stdout.write(
                f"  {'Created' if created else 'Updated'} rate: {component.code} - ${min_chg} MIN / ${rate}/kg"
            )
        
        return card
