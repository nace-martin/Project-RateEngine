from django.core.management.base import BaseCommand
from customers.models import Customer

class Command(BaseCommand):
    help = 'Checks if querying the Customer model hangs.'

    def handle(self, *args, **options):
        self.stdout.write('Attempting to query and iterate all Customer objects...')
        try:
            customers = Customer.objects.select_related('primary_address').all()
            count = 0
            for customer in customers:
                count += 1
                self.stdout.write(f'  - Found customer: {customer.company_name}')
            self.stdout.write(self.style.SUCCESS(f'Successfully iterated all customers. Total: {count}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))