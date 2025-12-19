# pricing_v4/management/commands/migrate_surcharges_to_unified.py
"""
Migrate Export and Import ancillary charges to the unified Surcharge model.

This command:
1. Reads distinct surcharge ProductCodes from ExportCOGS/ExportSellRate/ImportCOGS/ImportSellRate
2. Creates corresponding global Surcharge entries
3. Does NOT delete the original per-lane entries (for rollback safety)

Run with: python manage.py migrate_surcharges_to_unified
"""

from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from pricing_v4.models import (
    ProductCode, 
    Surcharge,
    ExportCOGS, ExportSellRate,
    ImportCOGS, ImportSellRate,
)


class Command(BaseCommand):
    help = 'Migrate Export/Import surcharges to the unified Surcharge model'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(f"{'DRY RUN: ' if dry_run else ''}Migrating surcharges to unified model...")
        
        created_count = 0
        skipped_count = 0
        
        # Define which ProductCodes are surcharges (not freight)
        # Freight is handled per-lane, surcharges should be global
        EXPORT_SURCHARGE_CODES = [
            'EXP-DOC', 'EXP-AWB', 'EXP-TERMINAL', 'EXP-BUILDUP',
            'EXP-SCREENING', 'EXP-AGENCY', 'EXP-CLEARANCE', 
            'EXP-PICKUP', 'EXP-FSC-PICKUP',
        ]
        
        IMPORT_SURCHARGE_CODES = [
            'IMP-DOC', 'IMP-AWB', 'IMP-TERMINAL', 'IMP-HANDLING',
            'IMP-SCREEN', 'IMP-AGENCY', 'IMP-CLEARANCE', 'IMP-CTO',
            'IMP-PICKUP', 'IMP-FSC', 'IMP-LOADING', 'IMP-CARTAGE',
            'IMP-FSC-CARTAGE',
        ]
        
        # Process Export COGS
        self.stdout.write("Processing Export COGS...")
        for code in EXPORT_SURCHARGE_CODES:
            try:
                pc = ProductCode.objects.get(code=code)
            except ProductCode.DoesNotExist:
                self.stdout.write(f"  SKIP: {code} (ProductCode not found)")
                skipped_count += 1
                continue
                
            # Find a representative rate (we take the first one as the global rate)
            cogs = ExportCOGS.objects.filter(product_code=pc).first()
            if not cogs:
                self.stdout.write(f"  SKIP: {code} (no COGS entries)")
                skipped_count += 1
                continue
            
            # Check if already exists
            if Surcharge.objects.filter(
                product_code=pc, 
                service_type='EXPORT_AIR',
                rate_side='COGS'
            ).exists():
                self.stdout.write(f"  SKIP: {code} (already exists)")
                skipped_count += 1
                continue
            
            # Determine rate type
            if cogs.is_additive:
                # Additive: both per_kg and flat
                rate_type = 'PER_KG'  # Primary type
                amount = cogs.rate_per_kg or Decimal('0')
            elif cogs.rate_per_shipment and not cogs.rate_per_kg:
                rate_type = 'FLAT'
                amount = cogs.rate_per_shipment
            else:
                rate_type = 'PER_KG'
                amount = cogs.rate_per_kg or Decimal('0')
            
            if not dry_run:
                Surcharge.objects.create(
                    product_code=pc,
                    rate_side='COGS',
                    service_type='EXPORT_AIR',
                    rate_type=rate_type,
                    amount=amount,
                    min_charge=cogs.min_charge,
                    max_charge=cogs.max_charge,
                    currency=cogs.currency,
                    valid_from=cogs.valid_from,
                    valid_until=cogs.valid_until,
                )
            self.stdout.write(self.style.SUCCESS(f"  CREATE: {code} COGS ({rate_type}: {amount})"))
            created_count += 1
        
        # Process Export Sell
        self.stdout.write("Processing Export Sell...")
        for code in EXPORT_SURCHARGE_CODES:
            try:
                pc = ProductCode.objects.get(code=code)
            except ProductCode.DoesNotExist:
                continue
                
            sell = ExportSellRate.objects.filter(product_code=pc).first()
            if not sell:
                continue
            
            if Surcharge.objects.filter(
                product_code=pc, 
                service_type='EXPORT_AIR',
                rate_side='SELL'
            ).exists():
                skipped_count += 1
                continue
            
            if sell.percent_rate:
                rate_type = 'PERCENT'
                amount = sell.percent_rate
            elif sell.is_additive:
                rate_type = 'PER_KG'
                amount = sell.rate_per_kg or Decimal('0')
            elif sell.rate_per_shipment and not sell.rate_per_kg:
                rate_type = 'FLAT'
                amount = sell.rate_per_shipment
            else:
                rate_type = 'PER_KG'
                amount = sell.rate_per_kg or Decimal('0')
            
            if not dry_run:
                Surcharge.objects.create(
                    product_code=pc,
                    rate_side='SELL',
                    service_type='EXPORT_AIR',
                    rate_type=rate_type,
                    amount=amount,
                    min_charge=sell.min_charge,
                    max_charge=sell.max_charge,
                    currency=sell.currency,
                    valid_from=sell.valid_from,
                    valid_until=sell.valid_until,
                )
            self.stdout.write(self.style.SUCCESS(f"  CREATE: {code} SELL ({rate_type}: {amount})"))
            created_count += 1
        
        # Process Import (similar logic)
        self.stdout.write("Processing Import COGS...")
        for code in IMPORT_SURCHARGE_CODES:
            try:
                pc = ProductCode.objects.get(code=code)
            except ProductCode.DoesNotExist:
                skipped_count += 1
                continue
                
            cogs = ImportCOGS.objects.filter(product_code=pc).first()
            if not cogs:
                skipped_count += 1
                continue
            
            # Determine if origin or destination
            # Import COGS from origin (AU) are IMPORT_ORIGIN, destination (PG) are IMPORT_DEST
            service_type = 'IMPORT_ORIGIN' if cogs.agent and cogs.agent.country_code == 'AU' else 'IMPORT_DEST'
            
            if Surcharge.objects.filter(
                product_code=pc, 
                service_type=service_type,
                rate_side='COGS'
            ).exists():
                skipped_count += 1
                continue
            
            if cogs.percent_rate:
                rate_type = 'PERCENT'
                amount = cogs.percent_rate
            elif cogs.is_additive:
                rate_type = 'PER_KG'
                amount = cogs.rate_per_kg or Decimal('0')
            elif cogs.rate_per_shipment and not cogs.rate_per_kg:
                rate_type = 'FLAT'
                amount = cogs.rate_per_shipment
            else:
                rate_type = 'PER_KG'
                amount = cogs.rate_per_kg or Decimal('0')
            
            if not dry_run:
                Surcharge.objects.create(
                    product_code=pc,
                    rate_side='COGS',
                    service_type=service_type,
                    rate_type=rate_type,
                    amount=amount,
                    min_charge=cogs.min_charge,
                    max_charge=cogs.max_charge,
                    currency=cogs.currency,
                    valid_from=cogs.valid_from,
                    valid_until=cogs.valid_until,
                )
            self.stdout.write(self.style.SUCCESS(f"  CREATE: {code} COGS ({service_type}: {amount})"))
            created_count += 1
        
        # Process Import Sell
        self.stdout.write("Processing Import Sell...")
        for code in IMPORT_SURCHARGE_CODES:
            try:
                pc = ProductCode.objects.get(code=code)
            except ProductCode.DoesNotExist:
                continue
                
            sell = ImportSellRate.objects.filter(product_code=pc).first()
            if not sell:
                continue
            
            # Import Sell rates are typically for destination (PG)
            service_type = 'IMPORT_DEST'
            
            if Surcharge.objects.filter(
                product_code=pc, 
                service_type=service_type,
                rate_side='SELL'
            ).exists():
                skipped_count += 1
                continue
            
            if sell.percent_rate:
                rate_type = 'PERCENT'
                amount = sell.percent_rate
            elif sell.is_additive:
                rate_type = 'PER_KG'
                amount = sell.rate_per_kg or Decimal('0')
            elif sell.rate_per_shipment and not sell.rate_per_kg:
                rate_type = 'FLAT'
                amount = sell.rate_per_shipment
            else:
                rate_type = 'PER_KG'
                amount = sell.rate_per_kg or Decimal('0')
            
            if not dry_run:
                Surcharge.objects.create(
                    product_code=pc,
                    rate_side='SELL',
                    service_type=service_type,
                    rate_type=rate_type,
                    amount=amount,
                    min_charge=sell.min_charge,
                    max_charge=sell.max_charge,
                    currency=sell.currency,
                    valid_from=sell.valid_from,
                    valid_until=sell.valid_until,
                )
            self.stdout.write(self.style.SUCCESS(f"  CREATE: {code} SELL ({service_type}: {amount})"))
            created_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Created: {created_count}, Skipped: {skipped_count}"
        ))
