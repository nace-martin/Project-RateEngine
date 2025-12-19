from django.core.management.base import BaseCommand
from pricing_v4.models import ImportCOGS, ImportSellRate, ProductCode

class Command(BaseCommand):
    help = 'Unseeds Import Data (COGS, Sell Rates, ProductCodes)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Unseeding Import Data")
        self.stdout.write("=" * 60)

        # 1. Delete Rate Tables
        ImportSellRate.objects.all().delete()
        ImportCOGS.objects.all().delete()
        
        # 2. Delete ProductCodes
        # Must delete Surcharges first (dependents)
        surcharges = ProductCode.objects.filter(domain='IMPORT', category='SURCHARGE')
        count = surcharges.count()
        surcharges.delete()
        self.stdout.write(f"- Deleted {count} Import Surcharge ProductCodes")

        # Now delete the rest
        others = ProductCode.objects.filter(domain='IMPORT')
        count = others.count()
        others.delete()
        self.stdout.write(f"- Deleted {count} remaining Import ProductCodes")

        self.stdout.write("=" * 60)
        self.stdout.write("Done")
