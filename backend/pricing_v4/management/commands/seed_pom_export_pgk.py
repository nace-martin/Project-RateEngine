# backend/pricing_v4/management/commands/seed_pom_export_pgk.py
"""
Seed POM Export Prepaid origin charges in PGK into LocalSellRate.

Creates missing ProductCodes (EXP-VCH, EXP-LPC) and then seeds 12 PGK-denominated
origin charges for Port Moresby (POM) Export Prepaid shipments.

Uses update_or_create to be idempotent — safe to run multiple times.

Usage:
    python manage.py seed_pom_export_pgk
    python manage.py seed_pom_export_pgk --dry-run   # Preview without changes
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import date

from pricing_v4.models import ProductCode, LocalSellRate


# ── Rate data ────────────────────────────────────────────────────────────────
# Each tuple: (product_code_id, rate_type, amount, min_charge, max_charge,
#              is_additive, additive_flat_amount, percent_of_product_code_id)
RATES = [
    # Origin Handling Charges
    (1010, 'FIXED',   '50.00',  None,    None,    False, None,    None),  # Documentation Fee
    (1011, 'FIXED',   '50.00',  None,    None,    False, None,    None),  # Air Waybill Fee
    (1040, 'PER_KG',  '0.20',   '45.00', None,    True,  '45.00', None),  # Security Surcharge (0.20/kg + K45 flat)
    (1030, 'FIXED',   '50.00',  None,    None,    False, None,    None),  # Terminal Fee
    (1031, 'PER_KG',  '0.20',   '50.00', None,    False, None,    None),  # Build-Up Fee
    (1071, 'FIXED',   '100.00', None,    None,    False, None,    None),  # Valuable Cargo Handling
    (1070, 'FIXED',   '250.00', None,    None,    False, None,    None),  # Dangerous Goods Acceptance
    (1072, 'FIXED',   '100.00', None,    None,    False, None,    None),  # Livestock Processing Fee

    # Clearance and Cartage Charges
    (1020, 'FIXED',   '300.00', None,    None,    False, None,    None),  # Customs Clearance
    (1021, 'FIXED',   '250.00', None,    None,    False, None,    None),  # Agency Fee
    (1050, 'PER_KG',  '1.50',   '95.00', '500.00', False, None,  None),  # Pick up Fee
    (1060, 'PERCENT', '10.00',  None,    None,    False, None,    1050),  # Fuel Surcharge (10% of Pickup)
]

# ── New ProductCodes required ────────────────────────────────────────────────
NEW_PRODUCT_CODES = [
    {
        'id': 1071,
        'code': 'EXP-VCH',
        'description': 'Valuable Cargo Handling',
        'domain': 'EXPORT',
        'category': 'HANDLING',
        'is_gst_applicable': True,
        'gst_rate': Decimal('0.10'),
        'gst_treatment': 'ZERO_RATED',
        'gl_revenue_code': '4110',
        'gl_cost_code': '5110',
        'default_unit': 'SHIPMENT',
    },
    {
        'id': 1072,
        'code': 'EXP-LPC',
        'description': 'Livestock Processing Fee',
        'domain': 'EXPORT',
        'category': 'HANDLING',
        'is_gst_applicable': True,
        'gst_rate': Decimal('0.10'),
        'gst_treatment': 'ZERO_RATED',
        'gl_revenue_code': '4110',
        'gl_cost_code': '5110',
        'default_unit': 'SHIPMENT',
    },
]

# ── Constants ────────────────────────────────────────────────────────────────
LOCATION = 'POM'
DIRECTION = 'EXPORT'
PAYMENT_TERM = 'PREPAID'
CURRENCY = 'PGK'
VALID_FROM = date(2025, 1, 1)
VALID_UNTIL = date(2025, 12, 31)


class Command(BaseCommand):
    help = 'Seed POM Export Prepaid PGK origin charges into LocalSellRate'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without committing to the database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created_pcs = 0
        created_rates = 0
        updated_rates = 0

        self.stdout.write('=' * 60)
        self.stdout.write('Seeding POM Export Prepaid PGK Rates')
        if dry_run:
            self.stdout.write(self.style.WARNING('  *** DRY RUN — no changes will be saved ***'))
        self.stdout.write('=' * 60)

        try:
            with transaction.atomic():
                # ── Phase 1: Ensure ProductCodes exist ───────────────────
                self.stdout.write('\n--- Phase 1: ProductCodes ---')
                for pc_data in NEW_PRODUCT_CODES:
                    pc_id = pc_data['id']
                    defaults = {k: v for k, v in pc_data.items() if k != 'id'}
                    obj, created = ProductCode.objects.update_or_create(
                        id=pc_id,
                        defaults=defaults,
                    )
                    action = 'Created' if created else 'Already exists'
                    created_pcs += int(created)
                    self.stdout.write(f'  {action}: {obj.code} (ID {obj.id}) — {obj.description}')

                # ── Phase 2: Seed LocalSellRate rows ─────────────────────
                self.stdout.write(f'\n--- Phase 2: LocalSellRate ({LOCATION}/{DIRECTION}/{PAYMENT_TERM}/{CURRENCY}) ---')
                for (pc_id, rate_type, amount, min_charge, max_charge,
                     is_additive, additive_flat, pct_of_pc_id) in RATES:

                    defaults = {
                        'rate_type': rate_type,
                        'amount': Decimal(amount),
                        'is_additive': is_additive,
                        'additive_flat_amount': Decimal(additive_flat) if additive_flat else None,
                        'min_charge': Decimal(min_charge) if min_charge else None,
                        'max_charge': Decimal(max_charge) if max_charge else None,
                        'valid_until': VALID_UNTIL,
                        'percent_of_product_code_id': pct_of_pc_id,
                    }

                    obj, created = LocalSellRate.objects.update_or_create(
                        product_code_id=pc_id,
                        location=LOCATION,
                        direction=DIRECTION,
                        payment_term=PAYMENT_TERM,
                        currency=CURRENCY,
                        valid_from=VALID_FROM,
                        defaults=defaults,
                    )

                    pc_code = ProductCode.objects.get(id=pc_id).code
                    if created:
                        created_rates += 1
                        self.stdout.write(self.style.SUCCESS(f'  Created: {pc_code} — {rate_type} {amount}'))
                    else:
                        updated_rates += 1
                        self.stdout.write(f'  Updated: {pc_code} — {rate_type} {amount}')

                if dry_run:
                    raise _DryRunRollback()

        except _DryRunRollback:
            self.stdout.write(self.style.WARNING('\n  Dry run complete — transaction rolled back.'))

        # ── Summary ──────────────────────────────────────────────────────
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'ProductCodes created : {created_pcs}')
        self.stdout.write(f'LocalSellRate created: {created_rates}')
        self.stdout.write(f'LocalSellRate updated: {updated_rates}')
        self.stdout.write('=' * 60)


class _DryRunRollback(Exception):
    """Raised to roll back the transaction in dry-run mode."""
    pass
