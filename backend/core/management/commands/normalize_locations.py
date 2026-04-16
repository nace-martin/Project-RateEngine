from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Location
from quotes.models import Quote

class Command(BaseCommand):
    help = 'Normalizes locations to use airport-backed codes and removes orphan legacy duplicates'

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
        orphan_dedupes = 0
        
        with transaction.atomic():
            # Pre-fetch all needed locations to avoid N+1 queries
            city_codes = list(mappings.keys())
            airport_codes = list(mappings.values())

            cities_by_code = {
                loc.code: loc
                for loc in Location.objects.filter(code__in=city_codes, kind='CITY')
            }
            airports_by_code = {
                loc.code: loc
                for loc in Location.objects.filter(code__in=airport_codes, kind='AIRPORT')
            }

            for city_code, airport_code in mappings.items():
                # Get the city and airport locations
                city_loc = cities_by_code.get(city_code)
                airport_loc = airports_by_code.get(airport_code)

                if not city_loc or not airport_loc:
                    self.stdout.write(self.style.ERROR("Location not found: Location matching query does not exist."))
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

            self.stdout.write("\nChecking for orphan airport duplicates...")
            canonical_airport_locations = {
                loc.code: loc
                for loc in Location.objects.filter(
                    kind=Location.Kind.AIRPORT,
                    airport__isnull=False,
                ).select_related("airport")
            }
            orphan_locations = (
                Location.objects.filter(
                    kind=Location.Kind.AIRPORT,
                    airport__isnull=True,
                )
                .exclude(code="")
                .order_by("code", "id")
            )

            for orphan_loc in orphan_locations:
                canonical_loc = canonical_airport_locations.get(orphan_loc.code)
                if not canonical_loc or canonical_loc.id == orphan_loc.id:
                    continue

                origin_quotes = Quote.objects.filter(origin_location=orphan_loc)
                dest_quotes = Quote.objects.filter(destination_location=orphan_loc)

                origin_count = origin_quotes.count()
                dest_count = dest_quotes.count()
                total_quotes += origin_count + dest_count
                orphan_dedupes += 1

                self.stdout.write(f"\nOrphan airport duplicate {orphan_loc.code}:")
                self.stdout.write(
                    f"  - Legacy row: {orphan_loc.id} ({orphan_loc.name})"
                )
                self.stdout.write(
                    f"  - Canonical row: {canonical_loc.id} ({canonical_loc.name})"
                )
                self.stdout.write(f"  - Origin quotes: {origin_count}")
                self.stdout.write(f"  - Destination quotes: {dest_count}")

                if not dry_run:
                    origin_quotes.update(origin_location=canonical_loc)
                    dest_quotes.update(destination_location=canonical_loc)
                    orphan_loc.delete()
                    self.stdout.write(
                        self.style.SUCCESS(f"  [OK] Merged and deleted orphan {orphan_loc.code}")
                    )
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nWould update {total_quotes} quotes and merge {orphan_dedupes} orphan airport duplicates"
                    )
                )
                raise Exception("Dry run - rolling back")
            else:
                self.stdout.write(self.style.SUCCESS(f"\n[OK] Successfully updated {total_quotes} quotes"))
                self.stdout.write(
                    self.style.SUCCESS(f"[OK] Deleted city/orphan locations, merged {orphan_dedupes} duplicates")
                )
