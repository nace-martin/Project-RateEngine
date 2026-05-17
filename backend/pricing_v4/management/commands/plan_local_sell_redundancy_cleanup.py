from django.core.management.base import BaseCommand
from django.db import transaction
from pricing_v4.models import LocalSellRate
from datetime import date

class Command(BaseCommand):
    help = 'Identify and optionally delete redundant specific-term LocalSellRate rows shadowed by ANY rows.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Execute deletion of redundant rows.')

    def handle(self, *args, **options):
        apply = options['apply']
        
        specific_rates = LocalSellRate.objects.exclude(payment_term='ANY')
        any_rates = LocalSellRate.objects.filter(payment_term='ANY')

        results = {
            'safe_to_delete_specific_term': [],
            'keep_specific_term_differs_from_any': [],
            'historical_only': [],
            'unsafe_overlap_conflict': []
        }

        today = date.today()

        for spec in specific_rates:
            overlapping_any = any_rates.filter(
                product_code=spec.product_code,
                location=spec.location,
                direction=spec.direction,
                currency=spec.currency,
                valid_from__lte=spec.valid_until,
                valid_until__gte=spec.valid_from
            )

            if not overlapping_any.exists():
                results['historical_only'].append(spec)
                continue

            if overlapping_any.count() > 1:
                results['unsafe_overlap_conflict'].append(spec)
                continue
            
            any_rate = overlapping_any.first()
            
            commercial_fields = [
                'rate_type', 'amount', 'is_additive', 'additive_flat_amount', 
                'min_charge', 'max_charge', 'weight_breaks', 'percent_of_product_code'
            ]
            
            differs = False
            for field in commercial_fields:
                val_spec = getattr(spec, field)
                val_any = getattr(any_rate, field)
                
                if val_spec != val_any:
                    differs = True
                    break
            
            if differs:
                results['keep_specific_term_differs_from_any'].append((spec, any_rate))
            else:
                results['safe_to_delete_specific_term'].append((spec, any_rate))

        self.stdout.write(self.style.SUCCESS("Plan Summary:"))
        self.stdout.write(f"  safe_to_delete_specific_term:        {len(results['safe_to_delete_specific_term'])}")
        self.stdout.write(f"  keep_specific_term_differs_from_any: {len(results['keep_specific_term_differs_from_any'])}")
        self.stdout.write(f"  historical_only:                     {len(results['historical_only'])}")
        self.stdout.write(f"  unsafe_overlap_conflict:             {len(results['unsafe_overlap_conflict'])}")

        if apply:
            if not results['safe_to_delete_specific_term']:
                self.stdout.write("Nothing to delete.")
                return

            with transaction.atomic():
                ids_to_delete = [spec.id for spec, any_rate in results['safe_to_delete_specific_term']]
                deleted_count, _ = LocalSellRate.objects.filter(id__in=ids_to_delete).delete()
                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} redundant specific-term rows."))
        else:
            self.stdout.write(self.style.WARNING("\nDRY RUN: No changes made. Use --apply to execute."))
