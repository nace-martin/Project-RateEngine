from django.core.management.base import BaseCommand
from pricing.models import Lane
from pricing.services.pricing_service import validate_break_monotonic

class Command(BaseCommand):
    help = "Validates that all lanes have monotonically decreasing per-kg break rates."

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting validation of all lane breaks...")
        lanes_with_warnings = 0
        
        # Eager load related models to avoid N+1 queries
        all_lanes = Lane.objects.all().select_related('ratecard', 'origin', 'dest')
        total_lanes = all_lanes.count()

        if total_lanes == 0:
            self.stdout.write(self.style.WARNING("No lanes found in the database to validate."))
            return

        for lane in all_lanes:
            warnings = validate_break_monotonic(lane.id)
            if warnings:
                lanes_with_warnings += 1
                self.stdout.write(self.style.WARNING(f"--- Lane {lane.id} ({lane.origin.iata}-{lane.dest.iata} on card '{lane.ratecard.name}') ---"))
                for warning in warnings:
                    self.stdout.write(f"  - {warning}")

        self.stdout.write("-" * 20)
        if lanes_with_warnings > 0:
            self.stdout.write(self.style.ERROR(f"\nValidation complete. Found issues in {lanes_with_warnings} out of {total_lanes} lanes."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nValidation complete. All {total_lanes} lanes look good."))
