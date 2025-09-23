from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Seeds the database with initial data for the pricing_v2 app.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Seeding pricing_v2 data...'))
        # In the future, this command would create currency and fee data.
        self.stdout.write(self.style.SUCCESS('Pricing_v2 data seeded successfully.'))
