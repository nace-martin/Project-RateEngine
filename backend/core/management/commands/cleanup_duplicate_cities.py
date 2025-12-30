from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import City, Airport, Port, Location

class Command(BaseCommand):
    help = 'Merges duplicate city records (e.g., "BNE" -> "Brisbane")'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be merged without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Mapping of IATA codes to proper city names
        IATA_TO_CITY = {
            'BNE': 'Brisbane',
            'SYD': 'Sydney',
            'CNS': 'Cairns',
            'POM': 'Port Moresby',
            'HKG': 'Hong Kong',
            'MNL': 'Manila',
            'HIR': 'Honiara',
            'SIN': 'Singapore',
            'VLI': 'Port Vila',
            'NAN': 'Nadi',
        }

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made\n"))

        with transaction.atomic():
            for iata, proper_name in IATA_TO_CITY.items():
                # Find cities with the IATA name
                iata_cities = City.objects.filter(name=iata)
                if not iata_cities.exists():
                    continue
                
                for iata_city in iata_cities:
                    # Find or ensure the proper city exists
                    try:
                        proper_city = City.objects.get(name=proper_name, country=iata_city.country)
                    except City.DoesNotExist:
                        self.stdout.write(self.style.NOTICE(f"Proper city '{proper_name}' for country {iata_city.country} does not exist. Renaming '{iata}' instead."))
                        if not dry_run:
                            iata_city.name = proper_name
                            iata_city.save(update_fields=['name'])
                        continue

                    if iata_city.id == proper_city.id:
                        continue

                    self.stdout.write(f"Merging '{iata_city.name}' into '{proper_city.name}' ({iata_city.country.code})")

                    # Update related objects
                    airports = Airport.objects.filter(city=iata_city)
                    ports = Port.objects.filter(city=iata_city)
                    locations = Location.objects.filter(city=iata_city)

                    if dry_run:
                        self.stdout.write(f"  Would update {airports.count()} airports, {ports.count()} ports, {locations.count()} locations")
                    else:
                        airports.update(city=proper_city)
                        ports.update(city=proper_city)
                        locations.update(city=proper_city)
                        iata_city.delete()
                        self.stdout.write(self.style.SUCCESS(f"  [OK] Merged and deleted '{iata}'"))

        self.stdout.write(self.style.SUCCESS("\nCleanup complete."))
