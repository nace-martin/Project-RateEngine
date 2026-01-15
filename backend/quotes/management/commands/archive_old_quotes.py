from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from quotes.models import Quote

class Command(BaseCommand):
    help = 'Soft-delete (archive) quotes older than 3 months.'

    def handle(self, *args, **options):
        # 3 months is approx 90 days. Using 90 days for simplicity and standard lib compatibility.
        cutoff_date = timezone.now() - timedelta(days=90)
        
        qs = Quote.objects.filter(created_at__lt=cutoff_date, is_archived=False)
        count = qs.count()
        
        if count > 0:
            self.stdout.write(f"Found {count} quotes older than {cutoff_date.date()} to archive.")
            updated_count = qs.update(is_archived=True)
            self.stdout.write(self.style.SUCCESS(f"Successfully archived {updated_count} quotes."))
        else:
            self.stdout.write("No quotes found eligible for archiving (older than 3 months).")
