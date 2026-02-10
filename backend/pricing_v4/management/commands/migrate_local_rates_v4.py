# backend/pricing_v4/management/commands/migrate_local_rates_v4.py
"""
Data Migration: Collapse local charges into LocalSellRate and LocalCOGSRate.

This command migrates local service rates from lane-based tables to location-based tables:

Sell Side:
- ExportSellRate (local categories) -> LocalSellRate (direction=EXPORT)
- ImportSellRate (local categories) -> LocalSellRate (direction=IMPORT)
- A2DDAPRate -> LocalSellRate (direction=IMPORT, supports PERCENT type)

Buy Side:
- ExportCOGS (local categories) -> LocalCOGSRate (direction=EXPORT)
- ImportCOGS (local categories) -> LocalCOGSRate (direction=IMPORT)

Usage:
    python manage.py migrate_local_rates_v4 --dry-run     # Preview changes
    python manage.py migrate_local_rates_v4               # Execute migration
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from decimal import Decimal
from collections import defaultdict

from pricing_v4.models import (
    ProductCode,
    ExportSellRate, ImportSellRate, ExportCOGS, ImportCOGS,
    LocalSellRate, LocalCOGSRate,
    Agent
)


# Categories considered "Local" (not lane-dependent)
LOCAL_CATEGORIES = ['CLEARANCE', 'CARTAGE', 'HANDLING', 'DOCUMENTATION', 'SCREENING']


class Command(BaseCommand):
    help = 'Migrate local charges from lane-based to location-based tables'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview migration without making changes',
        )
    
    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.conflicts = []
        self.created_sell = 0
        self.created_cogs = 0
        self.skipped_duplicates = 0
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN MODE ==='))
        
        try:
            with transaction.atomic():
                # Phase 1: Sell Side Migration
                self.migrate_export_sell_rates()
                self.migrate_import_sell_rates()
                self.migrate_a2d_dap_rates()
                
                # Phase 2: COGS Side Migration
                self.migrate_export_cogs()
                self.migrate_import_cogs()
                
                if self.dry_run:
                    # Rollback in dry-run mode
                    raise DryRunComplete()
                    
        except DryRunComplete:
            pass
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== MIGRATION SUMMARY ==='))
        self.stdout.write(f'LocalSellRate created: {self.created_sell}')
        self.stdout.write(f'LocalCOGSRate created: {self.created_cogs}')
        self.stdout.write(f'Duplicates skipped: {self.skipped_duplicates}')
        
        if self.conflicts:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('=== DATA CONFLICTS DETECTED ==='))
            for conflict in self.conflicts:
                self.stdout.write(self.style.WARNING(f'  - {conflict}'))
    
    def get_local_product_codes(self):
        """Get ProductCodes in local categories."""
        return ProductCode.objects.filter(category__in=LOCAL_CATEGORIES)
    
    def migrate_export_sell_rates(self):
        """Migrate ExportSellRate local charges to LocalSellRate (EXPORT)."""
        self.stdout.write('\n--- Migrating ExportSellRate (Local) -> LocalSellRate (EXPORT) ---')
        
        local_pcs = self.get_local_product_codes()
        rates = ExportSellRate.objects.filter(product_code__in=local_pcs)
        
        # Group by origin_airport to detect conflicts
        rate_by_origin = defaultdict(list)
        for rate in rates:
            key = (rate.product_code_id, rate.origin_airport, rate.currency)
            rate_by_origin[key].append(rate)
        
        for (pc_id, origin, currency), rate_list in rate_by_origin.items():
            # Check for conflicts (different amounts for same origin)
            amounts = set(r.rate_per_shipment or r.rate_per_kg for r in rate_list)
            if len(amounts) > 1:
                self.conflicts.append(
                    f"ExportSellRate conflict: PC={pc_id}, {origin} has {len(amounts)} different rates"
                )
            
            # Use the first rate (or could implement merge logic)
            rate = rate_list[0]
            self._create_local_sell_rate(
                product_code_id=rate.product_code_id,
                location=rate.origin_airport,
                direction='EXPORT',
                payment_term='ANY',  # Export local charges apply to all terms
                currency=rate.currency,
                rate=rate
            )
    
    def migrate_import_sell_rates(self):
        """Migrate ImportSellRate local charges to LocalSellRate (IMPORT)."""
        self.stdout.write('\n--- Migrating ImportSellRate (Local) -> LocalSellRate (IMPORT) ---')
        
        local_pcs = self.get_local_product_codes()
        rates = ImportSellRate.objects.filter(product_code__in=local_pcs)
        
        # Group by destination_airport
        rate_by_dest = defaultdict(list)
        for rate in rates:
            key = (rate.product_code_id, rate.destination_airport, rate.currency)
            rate_by_dest[key].append(rate)
        
        for (pc_id, dest, currency), rate_list in rate_by_dest.items():
            amounts = set(r.rate_per_shipment or r.rate_per_kg for r in rate_list)
            if len(amounts) > 1:
                self.conflicts.append(
                    f"ImportSellRate conflict: PC={pc_id}, {dest} has {len(amounts)} different rates"
                )
            
            rate = rate_list[0]
            self._create_local_sell_rate(
                product_code_id=rate.product_code_id,
                location=rate.destination_airport,
                direction='IMPORT',
                payment_term='COLLECT',  # Import local = Collect by default
                currency=rate.currency,
                rate=rate
            )
    
    def migrate_a2d_dap_rates(self):
        """Migrate A2DDAPRate to LocalSellRate (IMPORT)."""
        self.stdout.write('\n--- Migrating A2DDAPRate -> LocalSellRate (IMPORT) ---')
        
        try:
            from ratecards.models import A2DDAPRate
        except ImportError:
            self.stdout.write(self.style.WARNING('  A2DDAPRate model not found, skipping...'))
            return
        
        rates = A2DDAPRate.objects.all()
        
        for rate in rates:
            # Determine rate_type from A2DDAPRate fields
            rate_type = 'FIXED'
            amount = rate.rate or Decimal('0')
            
            if rate.percent_of_component:
                rate_type = 'PERCENT'
                amount = rate.percent_of_component
            elif rate.unit_basis == 'KG':
                rate_type = 'PER_KG'
            
            # Map payment_term
            payment_term = rate.payment_term if rate.payment_term in ['PREPAID', 'COLLECT'] else 'ANY'
            
            # Create LocalSellRate
            self._create_local_sell_rate_direct(
                product_code_id=rate.product_code_id if hasattr(rate, 'product_code_id') else None,
                location=rate.destination if hasattr(rate, 'destination') else rate.airport_code,
                direction='IMPORT',
                payment_term=payment_term,
                currency=rate.currency,
                rate_type=rate_type,
                amount=amount,
                min_charge=rate.min_charge,
                max_charge=rate.max_charge,
                valid_from=rate.valid_from if hasattr(rate, 'valid_from') else rate.effective_from,
                valid_until=rate.valid_until if hasattr(rate, 'valid_until') else rate.effective_until
            )
    
    def migrate_export_cogs(self):
        """Migrate ExportCOGS local charges to LocalCOGSRate (EXPORT)."""
        self.stdout.write('\n--- Migrating ExportCOGS (Local) -> LocalCOGSRate (EXPORT) ---')
        
        local_pcs = self.get_local_product_codes()
        cogs = ExportCOGS.objects.filter(product_code__in=local_pcs)
        
        # Group by origin_airport + agent/carrier
        cogs_by_origin = defaultdict(list)
        for c in cogs:
            counterparty = c.agent_id or c.carrier_id
            key = (c.product_code_id, c.origin_airport, c.currency, counterparty)
            cogs_by_origin[key].append(c)
        
        for (pc_id, origin, currency, _), cogs_list in cogs_by_origin.items():
            amounts = set(c.rate_per_shipment or c.rate_per_kg for c in cogs_list)
            if len(amounts) > 1:
                self.conflicts.append(
                    f"ExportCOGS conflict: PC={pc_id}, {origin} has {len(amounts)} different rates"
                )
            
            c = cogs_list[0]
            self._create_local_cogs_rate(
                product_code_id=c.product_code_id,
                location=c.origin_airport,
                direction='EXPORT',
                agent_id=c.agent_id,
                carrier_id=c.carrier_id,
                currency=c.currency,
                cogs=c
            )
    
    def migrate_import_cogs(self):
        """Migrate ImportCOGS local charges to LocalCOGSRate (IMPORT)."""
        self.stdout.write('\n--- Migrating ImportCOGS (Local) -> LocalCOGSRate (IMPORT) ---')
        
        local_pcs = self.get_local_product_codes()
        cogs = ImportCOGS.objects.filter(product_code__in=local_pcs)
        
        # Group by destination_airport + agent/carrier
        cogs_by_dest = defaultdict(list)
        for c in cogs:
            counterparty = c.agent_id or c.carrier_id
            key = (c.product_code_id, c.destination_airport, c.currency, counterparty)
            cogs_by_dest[key].append(c)
        
        for (pc_id, dest, currency, _), cogs_list in cogs_by_dest.items():
            amounts = set(c.rate_per_shipment or c.rate_per_kg for c in cogs_list)
            if len(amounts) > 1:
                self.conflicts.append(
                    f"ImportCOGS conflict: PC={pc_id}, {dest} has {len(amounts)} different rates"
                )
            
            c = cogs_list[0]
            self._create_local_cogs_rate(
                product_code_id=c.product_code_id,
                location=c.destination_airport,
                direction='IMPORT',
                agent_id=c.agent_id,
                carrier_id=c.carrier_id,
                currency=c.currency,
                cogs=c
            )
    
    def _create_local_sell_rate(self, product_code_id, location, direction, payment_term, currency, rate):
        """Create LocalSellRate from ExportSellRate/ImportSellRate."""
        # Determine rate_type and amount
        is_additive = getattr(rate, 'is_additive', False)
        additive_flat_amount = None
        if rate.rate_per_kg:
            rate_type = 'PER_KG'
            amount = rate.rate_per_kg
            if is_additive and rate.rate_per_shipment:
                additive_flat_amount = rate.rate_per_shipment
        else:
            rate_type = 'FIXED'
            amount = rate.rate_per_shipment or Decimal('0')
        
        self._create_local_sell_rate_direct(
            product_code_id=product_code_id,
            location=location,
            direction=direction,
            payment_term=payment_term,
            currency=currency,
            rate_type=rate_type,
            amount=amount,
            is_additive=is_additive,
            additive_flat_amount=additive_flat_amount,
            min_charge=rate.min_charge,
            max_charge=getattr(rate, 'max_charge', None),
            valid_from=rate.valid_from,
            valid_until=rate.valid_until
        )
    
    def _create_local_sell_rate_direct(self, **kwargs):
        """Create LocalSellRate with given params."""
        # Check for existing
        existing = LocalSellRate.objects.filter(
            product_code_id=kwargs['product_code_id'],
            location=kwargs['location'],
            direction=kwargs['direction'],
            payment_term=kwargs['payment_term'],
            currency=kwargs['currency'],
            valid_from=kwargs['valid_from']
        ).first()
        
        if existing:
            self.skipped_duplicates += 1
            return
        
        if kwargs['product_code_id']:
            LocalSellRate.objects.create(
                product_code_id=kwargs['product_code_id'],
                location=kwargs['location'],
                direction=kwargs['direction'],
                payment_term=kwargs['payment_term'],
                currency=kwargs['currency'],
                rate_type=kwargs.get('rate_type', 'FIXED'),
                amount=kwargs['amount'],
                is_additive=kwargs.get('is_additive', False),
                additive_flat_amount=kwargs.get('additive_flat_amount'),
                min_charge=kwargs.get('min_charge'),
                max_charge=kwargs.get('max_charge'),
                valid_from=kwargs['valid_from'],
                valid_until=kwargs['valid_until']
            )
            self.created_sell += 1
            self.stdout.write(f'  Created LocalSellRate: {kwargs["location"]} ({kwargs["direction"]})')
    
    def _create_local_cogs_rate(self, product_code_id, location, direction, agent_id, carrier_id, currency, cogs):
        """Create LocalCOGSRate from ExportCOGS/ImportCOGS."""
        # Determine rate_type and amount
        is_additive = getattr(cogs, 'is_additive', False)
        additive_flat_amount = None
        if cogs.rate_per_kg:
            rate_type = 'PER_KG'
            amount = cogs.rate_per_kg
            if is_additive and cogs.rate_per_shipment:
                additive_flat_amount = cogs.rate_per_shipment
        else:
            rate_type = 'FIXED'
            amount = cogs.rate_per_shipment or Decimal('0')
        
        # Check for existing
        existing = LocalCOGSRate.objects.filter(
            product_code_id=product_code_id,
            location=location,
            direction=direction,
            agent_id=agent_id,
            carrier_id=carrier_id,
            currency=currency,
            valid_from=cogs.valid_from
        ).first()
        
        if existing:
            self.skipped_duplicates += 1
            return
        
        # Need at least one counterparty
        if not agent_id and not carrier_id:
            self.stdout.write(self.style.WARNING(f'  Skipping COGS with no counterparty: PC={product_code_id}'))
            return
        
        LocalCOGSRate.objects.create(
            product_code_id=product_code_id,
            location=location,
            direction=direction,
            agent_id=agent_id,
            carrier_id=carrier_id,
            currency=currency,
            rate_type=rate_type,
            amount=amount,
            is_additive=is_additive,
            additive_flat_amount=additive_flat_amount,
            min_charge=cogs.min_charge,
            max_charge=getattr(cogs, 'max_charge', None),
            valid_from=cogs.valid_from,
            valid_until=cogs.valid_until
        )
        self.created_cogs += 1
        self.stdout.write(f'  Created LocalCOGSRate: {location} ({direction})')


class DryRunComplete(Exception):
    """Raised to rollback transaction in dry-run mode."""
    pass
