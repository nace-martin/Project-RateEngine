from django.core.management.base import BaseCommand
from django.db import transaction
from pricing_v4.models import DomesticCOGS

class Command(BaseCommand):
    help = 'Clears all DomesticCOGS records (for refactoring to normalized design)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Clearing DomesticCOGS records")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            count = DomesticCOGS.objects.count()
            DomesticCOGS.objects.all().delete()
            self.stdout.write(f"Deleted {count} DomesticCOGS records")
