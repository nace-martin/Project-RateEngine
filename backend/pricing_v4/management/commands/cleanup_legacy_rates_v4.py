# backend/pricing_v4/management/commands/cleanup_legacy_rates_v4.py
"""
Cleanup: Remove migrated local charges from lane-based tables.

This command deletes local service rates from the legacy lane-based tables
after they have been migrated to LocalSellRate and LocalCOGSRate.

WARNING: Run this ONLY after migrate_local_rates_v4 and verification!

Actions:
- DELETE from ExportSellRate WHERE category IN LOCAL_CATEGORIES
- DELETE from ImportSellRate WHERE category IN LOCAL_CATEGORIES
- DELETE from ExportCOGS WHERE category IN LOCAL_CATEGORIES
- DELETE from ImportCOGS WHERE category IN LOCAL_CATEGORIES

Usage:
    python manage.py cleanup_legacy_rates_v4 --dry-run     # Preview deletes
    python manage.py cleanup_legacy_rates_v4               # Execute cleanup
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import (
    ProductCode,
    ExportSellRate, ImportSellRate, ExportCOGS, ImportCOGS,
    LocalSellRate, LocalCOGSRate
)


# Categories considered "Local" (not lane-dependent)
LOCAL_CATEGORIES = ['CLEARANCE', 'CARTAGE', 'HANDLING', 'DOCUMENTATION', 'SCREENING']


class Command(BaseCommand):
    help = 'Delete migrated local charges from legacy lane-based tables'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview deletions without making changes',
        )
        parser.add_argument(
            '--skip-verification',
            action='store_true',
            help='Skip verification that data was migrated (DANGEROUS)',
        )
    
    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.skip_verification = options['skip_verification']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN MODE ==='))
        
        # Verify migration was run
        if not self.skip_verification:
            sell_count = LocalSellRate.objects.count()
            cogs_count = LocalCOGSRate.objects.count()
            
            if sell_count == 0 and cogs_count == 0:
                self.stdout.write(self.style.ERROR(
                    'ERROR: No records in LocalSellRate/LocalCOGSRate. '
                    'Run migrate_local_rates_v4 first!'
                ))
                return
            
            self.stdout.write(f'Found {sell_count} LocalSellRate and {cogs_count} LocalCOGSRate records.')
        
        # Get local product codes
        local_pcs = ProductCode.objects.filter(category__in=LOCAL_CATEGORIES)
        
        self.stdout.write(f'\nLocal categories to clean: {LOCAL_CATEGORIES}')
        self.stdout.write(f'Matching ProductCodes: {local_pcs.count()}')
        
        # Count records to delete
        export_sell_count = ExportSellRate.objects.filter(product_code__in=local_pcs).count()
        import_sell_count = ImportSellRate.objects.filter(product_code__in=local_pcs).count()
        export_cogs_count = ExportCOGS.objects.filter(product_code__in=local_pcs).count()
        import_cogs_count = ImportCOGS.objects.filter(product_code__in=local_pcs).count()
        
        self.stdout.write('\n--- Records to Delete ---')
        self.stdout.write(f'  ExportSellRate (local): {export_sell_count}')
        self.stdout.write(f'  ImportSellRate (local): {import_sell_count}')
        self.stdout.write(f'  ExportCOGS (local): {export_cogs_count}')
        self.stdout.write(f'  ImportCOGS (local): {import_cogs_count}')
        
        total = export_sell_count + import_sell_count + export_cogs_count + import_cogs_count
        self.stdout.write(f'\n  TOTAL: {total} records')
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete. No changes made.'))
            return
        
        # Confirm before proceeding
        self.stdout.write(self.style.WARNING('\n*** THIS WILL DELETE DATA ***'))
        
        try:
            with transaction.atomic():
                # Delete ExportSellRate
                deleted, _ = ExportSellRate.objects.filter(product_code__in=local_pcs).delete()
                self.stdout.write(f'Deleted {deleted} ExportSellRate records')
                
                # Delete ImportSellRate
                deleted, _ = ImportSellRate.objects.filter(product_code__in=local_pcs).delete()
                self.stdout.write(f'Deleted {deleted} ImportSellRate records')
                
                # Delete ExportCOGS
                deleted, _ = ExportCOGS.objects.filter(product_code__in=local_pcs).delete()
                self.stdout.write(f'Deleted {deleted} ExportCOGS records')
                
                # Delete ImportCOGS
                deleted, _ = ImportCOGS.objects.filter(product_code__in=local_pcs).delete()
                self.stdout.write(f'Deleted {deleted} ImportCOGS records')
            
            self.stdout.write(self.style.SUCCESS('\nCleanup complete!'))
            self.stdout.write(self.style.WARNING(
                '\nNOTE: A2DDAPRate table still exists in ratecards app. '
                'Consider creating a migration to remove it.'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'ERROR during cleanup: {e}'))
            raise
