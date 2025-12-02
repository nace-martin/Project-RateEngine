from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Location, Airport
from quotes.models import Quote

class Command(BaseCommand):
    help = 'Normalizes locations to use airport codes instead of city codes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made\n"))
        
        # Mapping of city codes to airport codes
        mappings = {
            'BRI': 'BNE',  # Brisbane City -> Brisbane Airport
            'POR': 'POM',  # Port Moresby City -> Port Moresby Airport
        }
        
        total_quotes = 0
        
        with transaction.atomic():
            for city_code, airport_code in mappings.items():
                # Get the city and airport locations
                try:
                    city_loc = Location.objects.get(code=city_code, kind='CITY')
                    airport_loc = Location.objects.get(code=airport_code, kind='AIRPORT')
                except Location.DoesNotExist as e:
                    self.stdout.write(self.style.ERROR(f"Location not found: {e}"))
                    continue
                
                # Update quotes using this city location
                origin_quotes = Quote.objects.filter(origin_location=city_loc)
                dest_quotes = Quote.objects.filter(destination_location=city_loc)
                
                origin_count = origin_quotes.count()
                dest_count = dest_quotes.count()
                total_quotes += origin_count + dest_count
                
                self.stdout.write(f"\n{city_code} -> {airport_code}:")
                self.stdout.write(f"  - Origin quotes: {origin_count}")
                self.stdout.write(f"  - Destination quotes: {dest_count}")
                
                if not dry_run:
                    origin_quotes.update(origin_location=airport_loc)
                    dest_quotes.update(destination_location=airport_loc)
                    
                    # Delete the city location
                    city_loc.delete()
                    self.stdout.write(self.style.SUCCESS(f"  [OK] Updated and deleted {city_code}"))
            
            if dry_run:
                self.stdout.write(self.style.WARNING(f"\nWould update {total_quotes} quotes"))
                raise Exception("Dry run - rolling back")
            else:
                self.stdout.write(self.style.SUCCESS(f"\n[OK] Successfully updated {total_quotes} quotes"))
                self.stdout.write(self.style.SUCCESS("[OK] Deleted city locations"))
