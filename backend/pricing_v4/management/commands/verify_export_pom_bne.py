# backend/pricing_v4/management/commands/verify_export_pom_bne.py
"""
Verify Export POM→BNE Corridor End-to-End

Rule 9: One corridor must work end-to-end before expanding.

Verification checklist:
✓ Rate selection (correct rates found)
✓ Margin (positive, reasonable)
✓ Currency (PGK for Export Prepaid)
✓ GST (zero for Export)
"""

from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand

from pricing_v4.models import ProductCode
from pricing_v4.engine.export_engine import ExportPricingEngine


class Command(BaseCommand):
    help = 'Verify Export D2A POM→BNE corridor end-to-end'

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write("VERIFICATION: Export Air D2A Prepaid POM→BNE")
        self.stdout.write("=" * 70)
        
        # Test parameters
        origin = 'POM'
        destination = 'BNE'
        quote_date = date.today()
        chargeable_weight = Decimal('150.00')  # 150kg test shipment
        
        self.stdout.write(f"\nTest Parameters:")
        self.stdout.write(f"  Origin: {origin}")
        self.stdout.write(f"  Destination: {destination}")
        self.stdout.write(f"  Quote Date: {quote_date}")
        self.stdout.write(f"  Chargeable Weight: {chargeable_weight} kg")
        
        # Get all Export ProductCodes
        export_codes = ProductCode.objects.filter(domain=ProductCode.DOMAIN_EXPORT)
        product_code_ids = list(export_codes.values_list('id', flat=True))
        
        self.stdout.write(f"\nProductCodes to quote: {len(product_code_ids)}")
        
        # Initialize engine
        engine = ExportPricingEngine(
            quote_date=quote_date,
            origin=origin,
            destination=destination,
            chargeable_weight_kg=chargeable_weight,
        )
        
        # Calculate quote
        result = engine.calculate_quote(product_code_ids)
        
        # Display results
        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(f"{'Code':<15} {'Description':<25} {'COGS':>10} {'SELL':>10} {'Margin':>10} {'GST':>8}")
        self.stdout.write("-" * 70)
        
        all_passed = True
        
        for line in result.lines:
            self.stdout.write(
                f"{line.product_code:<15} "
                f"{line.description[:24]:<25} "
                f"{line.cost_amount:>10.2f} "
                f"{line.sell_amount:>10.2f} "
                f"{line.margin_amount:>10.2f} "
                f"{line.gst_amount:>8.2f}"
            )
            
            # Verification checks
            if line.is_rate_missing:
                self.stdout.write(self.style.WARNING(f"  ⚠ Missing rate"))
                all_passed = False
            
            if line.cost_amount > 0 and line.margin_amount <= 0:
                self.stdout.write(self.style.ERROR(f"  ✗ Negative or zero margin!"))
                all_passed = False
        
        self.stdout.write("-" * 70)
        self.stdout.write(
            f"{'TOTALS':<15} "
            f"{'':<25} "
            f"{result.total_cost:>10.2f} "
            f"{result.total_sell:>10.2f} "
            f"{result.total_margin:>10.2f} "
            f"{result.total_gst:>8.2f}"
        )
        self.stdout.write(f"\nTotal Sell (incl GST): {result.total_sell_incl_gst:.2f} {result.currency}")
        
        # Verification summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("VERIFICATION CHECKLIST")
        self.stdout.write("=" * 70)
        
        # Check 1: Rate selection
        rates_found = sum(1 for line in result.lines if not line.is_rate_missing)
        rates_missing = sum(1 for line in result.lines if line.is_rate_missing)
        if rates_found > 0 and rates_missing == 0:
            self.stdout.write(self.style.SUCCESS(f"✓ Rate Selection: {rates_found} rates found, 0 missing"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠ Rate Selection: {rates_found} found, {rates_missing} missing"))
            all_passed = False
        
        # Check 2: Margin
        if result.total_margin > 0:
            margin_pct = (result.total_margin / result.total_cost * 100) if result.total_cost > 0 else Decimal('0')
            self.stdout.write(self.style.SUCCESS(f"✓ Margin: {result.total_margin:.2f} PGK ({margin_pct:.1f}%)"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ Margin: {result.total_margin:.2f} PGK (must be positive)"))
            all_passed = False
        
        # Check 3: Currency
        if result.currency == 'PGK':
            self.stdout.write(self.style.SUCCESS(f"✓ Currency: {result.currency} (correct for Export Prepaid)"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ Currency: {result.currency} (expected PGK)"))
            all_passed = False
        
        # Check 4: GST (Export = 0)
        if result.total_gst == 0:
            self.stdout.write(self.style.SUCCESS(f"✓ GST: {result.total_gst:.2f} (correct - Export is GST-free)"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠ GST: {result.total_gst:.2f} (Export should be GST-free)"))
        
        # Final verdict
        self.stdout.write("\n" + "=" * 70)
        if all_passed:
            self.stdout.write(self.style.SUCCESS("✓ CORRIDOR VERIFIED: Export POM→BNE is PASSING"))
        else:
            self.stdout.write(self.style.ERROR("✗ CORRIDOR FAILED: See issues above"))
        self.stdout.write("=" * 70)
