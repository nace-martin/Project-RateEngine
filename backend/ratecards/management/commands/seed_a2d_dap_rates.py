"""
Management command to seed A2D DAP rate cards.

Seeds rate cards for Import A2D DAP quotes:
- PREPAID (AUD/USD): Partner agent quotes - FCY passthrough
- COLLECT (PGK): Local customer quotes - PGK passthrough (no FX/margin)
"""

from django.core.management.base import BaseCommand
from decimal import Decimal
from ratecards.models import A2DDAPRate
from services.models import ServiceComponent


class Command(BaseCommand):
    help = 'Seeds A2D DAP rate cards for PREPAID (AUD/USD) and COLLECT (PGK)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing rates and reseed',
        )

    def handle(self, *args, **options):
        force = options['force']
        
        if force:
            deleted_count, _ = A2DDAPRate.objects.all().delete()
            self.stdout.write(f"Deleted {deleted_count} existing A2D DAP rates")
        
        # =====================================================
        # PREPAID RATES (Partner Agent - FCY passthrough)
        # =====================================================
        # Format: (component_code, unit_basis, rate, min, max, percent_of_code, order)
        
        AUD_PREPAID_RATES = [
            ('CLEARANCE', 'AWB', '145.00', None, None, None, 1),
            ('AGENCY_IMP', 'AWB', '120.00', None, None, None, 2),
            ('DOC_IMP', 'AWB', '80.00', None, None, None, 3),
            ('HANDLING', 'AWB', '80.00', None, None, None, 4),
            ('TERM_INT', 'AWB', '80.00', None, None, None, 5),
            ('CARTAGE', 'KG', '0.50', '50.00', '400.00', None, 6),
            ('CARTAGE_FUEL', 'PERCENTAGE', '10.00', None, None, 'CARTAGE', 7),
        ]
        
        USD_PREPAID_RATES = [
            ('CLEARANCE', 'AWB', '105.00', None, None, None, 1),
            ('AGENCY_IMP', 'AWB', '90.00', None, None, None, 2),
            ('DOC_IMP', 'AWB', '60.00', None, None, None, 3),
            ('HANDLING', 'AWB', '60.00', None, None, None, 4),
            ('TERM_INT', 'AWB', '60.00', None, None, None, 5),
            ('CARTAGE', 'KG', '0.50', '50.00', '250.00', None, 6),
            ('CARTAGE_FUEL', 'PERCENTAGE', '10.00', None, None, 'CARTAGE', 7),
        ]
        
        # =====================================================
        # COLLECT RATES (Local Customer - PGK passthrough)
        # From user-provided rate card - no FX/margin applied
        # =====================================================
        
        PGK_COLLECT_RATES = [
            ('CLEARANCE', 'AWB', '300.00', None, None, None, 1),      # PGK 300.00
            ('AGENCY_IMP', 'AWB', '250.00', None, None, None, 2),     # PGK 250.00
            ('DOC_IMP', 'AWB', '165.00', None, None, None, 3),        # PGK 165.00
            ('HANDLING', 'AWB', '165.00', None, None, None, 4),       # PGK 165.00
            ('TERM_INT', 'AWB', '165.00', None, None, None, 5),       # PGK 165.00
            ('CARTAGE', 'KG', '1.50', '95.00', '500.00', None, 6),    # K1.50/kg, Min 95, Max 500
            ('CARTAGE_FUEL', 'PERCENTAGE', '10.00', None, None, 'CARTAGE', 7),  # 10% of Cartage
        ]
        
        # Ensure service components exist
        required_components = ['CLEARANCE', 'AGENCY_IMP', 'DOC_IMP', 'HANDLING', 'TERM_INT', 'CARTAGE', 'CARTAGE_FUEL']
        missing_components = []
        
        for code in required_components:
            if not ServiceComponent.objects.filter(code=code).exists():
                missing_components.append(code)
        
        if missing_components:
            self.stdout.write(
                self.style.WARNING(
                    f"Missing service components: {', '.join(missing_components)}. "
                    "Creating them now..."
                )
            )
            for code in missing_components:
                ServiceComponent.objects.create(
                    code=code,
                    description=code.replace('_', ' ').title(),
                    leg='DESTINATION',
                    cost_type='COGS',
                    mode='AIR',
                )
                self.stdout.write(f"  Created: {code}")
        
        # Seed all rates
        all_rate_sets = [
            ('PREPAID', 'AUD', AUD_PREPAID_RATES),
            ('PREPAID', 'USD', USD_PREPAID_RATES),
            ('COLLECT', 'PGK', PGK_COLLECT_RATES),  # COLLECT uses PGK rates directly
        ]
        
        created_count = 0
        skipped_count = 0
        
        for payment_term, currency, rates in all_rate_sets:
            self.stdout.write(f"\nSeeding {payment_term} {currency} rates...")
            
            for rate_data in rates:
                comp_code, unit_basis, rate, min_charge, max_charge, percent_of_code, order = rate_data
                
                # Get component
                try:
                    component = ServiceComponent.objects.get(code=comp_code)
                except ServiceComponent.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f"  Component {comp_code} not found, skipping")
                    )
                    continue
                
                # Get percent_of_component if needed
                percent_of_component = None
                if percent_of_code:
                    try:
                        percent_of_component = ServiceComponent.objects.get(code=percent_of_code)
                    except ServiceComponent.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(f"  Percent-of component {percent_of_code} not found")
                        )
                        continue
                
                # Check if already exists
                existing = A2DDAPRate.objects.filter(
                    payment_term=payment_term,
                    currency=currency,
                    service_component=component
                ).first()
                
                if existing and not force:
                    skipped_count += 1
                    self.stdout.write(f"  Skipped: {comp_code} (already exists)")
                    continue
                
                # Create or update
                A2DDAPRate.objects.update_or_create(
                    payment_term=payment_term,
                    currency=currency,
                    service_component=component,
                    defaults={
                        'unit_basis': unit_basis,
                        'rate': Decimal(rate),
                        'min_charge': Decimal(min_charge) if min_charge else None,
                        'max_charge': Decimal(max_charge) if max_charge else None,
                        'percent_of_component': percent_of_component,
                        'display_order': order,
                        'is_active': True,
                    }
                )
                created_count += 1
                self.stdout.write(f"  Created: {comp_code} = {rate} {unit_basis}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Created: {created_count}, Skipped: {skipped_count}"
            )
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                "\nRate Card Summary:"
                "\n  PREPAID AUD: 7 rates (FCY passthrough for AU origin)"
                "\n  PREPAID USD: 7 rates (FCY passthrough for SG/CN/etc)"
                "\n  COLLECT PGK: 7 rates (PGK passthrough for local customers)"
            )
        )
