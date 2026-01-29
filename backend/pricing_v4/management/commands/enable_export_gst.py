# backend/pricing_v4/management/commands/enable_export_gst.py
"""
Management command to configure GST rules for Export and Import ProductCodes.

GST Rules (PNG jurisdiction):
- GST 10% applies to services supplied IN Papua New Guinea only
- International freight is EXEMPT
- Services performed overseas are EXEMPT

Export Quotes (goods leaving PNG):
    ✅ Origin Charges  → GST 10% (services performed in PNG)
    ❌ Air Freight     → EXEMPT (international transport)
    ❌ Dest Charges    → EXEMPT (services performed overseas)

Import Quotes (goods arriving to PNG):
    ❌ Origin Charges  → EXEMPT (services performed overseas)
    ❌ Air Freight     → EXEMPT (international transport)
    ✅ Dest Charges    → GST 10% (services performed in PNG)

Usage:
    python manage.py enable_export_gst
"""

from django.core.management.base import BaseCommand
from pricing_v4.models import ProductCode


class Command(BaseCommand):
    help = 'Configure GST for Export and Import ProductCodes based on PNG tax rules'

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write("Configuring GST for Export & Import ProductCodes (PNG Rules)")
        self.stdout.write("=" * 70)
        
        # =====================================================================
        # EXPORT: GST on Origin services only (PNG based)
        # =====================================================================
        self.stdout.write("\n[EXPORT] Setting GST rules...")
        
        # Export codes that SHOULD have GST (Origin/PNG services)
        export_gst_codes = [
            'EXP-DOC', 'EXP-AWB', 'EXP-CLEAR', 'EXP-AGENCY',
            'EXP-TERM', 'EXP-BUILDUP', 'EXP-SCREEN',
            'EXP-PICKUP', 'EXP-FSC-PICKUP', 'EXP-DG'
        ]
        
        # Export codes that should NOT have GST (International/Overseas)
        export_no_gst_codes = [
            'EXP-FRT-AIR',        # International Air Freight
            'EXP-CLEAR-DEST',     # Overseas clearance
            'EXP-DELIVERY-DEST',  # Overseas delivery
        ]
        
        for code in export_gst_codes:
            self._set_gst(code, True, 'STANDARD')
        
        for code in export_no_gst_codes:
            self._set_gst(code, False, 'ZERO_RATED')
        
        # =====================================================================
        # IMPORT: GST on Destination services only (PNG based)
        # =====================================================================
        self.stdout.write("\n[IMPORT] Setting GST rules...")
        
        # Import codes that SHOULD have GST (Destination/PNG services)
        import_gst_codes = [
            'IMP-CLEAR', 'IMP-AGENCY-DEST', 'IMP-DOC-DEST',
            'IMP-HANDLING-DEST', 'IMP-LOADING-DEST',
            'IMP-CARTAGE-DEST', 'IMP-FSC-CARTAGE-DEST'
        ]
        
        # Import codes that should NOT have GST (International/Overseas)
        import_no_gst_codes = [
            'IMP-FRT-AIR',        # International Air Freight
            'IMP-DOC-ORIGIN',     # Overseas documentation
            'IMP-AWB-ORIGIN',     # Overseas AWB
            'IMP-AGENCY-ORIGIN',  # Overseas agency
            'IMP-CTO-ORIGIN',     # Overseas terminal
            'IMP-SCREEN-ORIGIN',  # Overseas screening
            'IMP-PICKUP',         # Overseas pickup
            'IMP-FSC-PICKUP',     # Overseas pickup FSC
        ]
        
        for code in import_gst_codes:
            self._set_gst(code, True, 'STANDARD')
        
        for code in import_no_gst_codes:
            self._set_gst(code, False, 'ZERO_RATED')
        
        # =====================================================================
        # Summary
        # =====================================================================
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✓ GST configuration complete"))
        self.stdout.write("=" * 70)
        self._print_summary()
    
    def _set_gst(self, code: str, is_applicable: bool, treatment: str):
        """Update GST settings for a ProductCode."""
        from decimal import Decimal
        try:
            pc = ProductCode.objects.get(code=code)
            pc.is_gst_applicable = is_applicable
            pc.gst_treatment = treatment
            # Set gst_rate to 10% if applicable, otherwise 0
            pc.gst_rate = Decimal('0.10') if is_applicable else Decimal('0')
            pc.save()
            status = "GST 10%" if is_applicable else "EXEMPT"
            self.stdout.write(f"  {code:<22} → {status}")
        except ProductCode.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"  {code:<22} → NOT FOUND"))
    
    def _print_summary(self):
        """Print summary table of all GST settings."""
        self.stdout.write("\nFinal GST Configuration:")
        self.stdout.write("-" * 70)
        
        for domain in ['EXPORT', 'IMPORT']:
            self.stdout.write(f"\n{domain}:")
            codes = ProductCode.objects.filter(domain=domain).order_by('category', 'code')
            for pc in codes:
                gst = "GST 10%" if pc.is_gst_applicable else "EXEMPT"
                self.stdout.write(f"  {pc.code:<22} | {pc.category:<15} | {gst}")
