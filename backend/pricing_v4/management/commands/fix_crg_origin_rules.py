from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from pricing_v4.models import ProductCode, CommodityChargeRule
from core.commodity import normalize_commodity_code

class Command(BaseCommand):
    help = 'Fixes missing CommodityChargeRule entries for GCR import origin charges on D2A and D2D.'

    def handle(self, *args, **options):
        self.stdout.write("Checking GCR CommodityChargeRule entries for Origin Charges...\n")
        
        target_codes = {
            'IMP-SCREEN-ORIGIN': 2040, # X-Ray Screening Fee
            'IMP-CTO-ORIGIN': 2030,    # CTO Fee
            'IMP-DOC-ORIGIN': 2010,    # Export Document Fee
            'IMP-AGENCY-ORIGIN': 2012, # Export Agency Fee
            'IMP-AWB-ORIGIN': 2011,    # Origin AWB Fee
            'IMP-PICKUP': 2050,        # Pick Up - Metro BNE/SYD
            'IMP-FSC-PICKUP': 2060,    # Fuel Surcharge - Pickup
        }
        
        target_scopes = ['D2A', 'D2D']
        commodities = [normalize_commodity_code('GCR')]
        effective_from = date.today().replace(month=1, day=1)
        
        rows_found = 0
        rows_created = 0

        with transaction.atomic():
            for code, expected_id in target_codes.items():
                try:
                    pc = ProductCode.objects.get(code=code)
                except ProductCode.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"ProductCode {code} not found in database. Skipping."))
                    continue
                
                if pc.id != expected_id:
                    self.stdout.write(self.style.WARNING(f"ProductCode {code} ID mismatch: Expected {expected_id}, got {pc.id}"))

                for scope in target_scopes:
                    for commodity in commodities:
                        rule, created = CommodityChargeRule.objects.get_or_create(
                            commodity_code=commodity,
                            shipment_type='IMPORT',
                            service_scope=scope,
                            product_code=pc,
                            defaults={
                                'trigger_mode': CommodityChargeRule.TRIGGER_MODE_AUTO,
                                'is_active': True,
                                'effective_from': effective_from,
                            }
                        )
                        
                        if created:
                            rows_created += 1
                            self.stdout.write(self.style.SUCCESS(f"Created rule for {code} under {commodity} / {scope}"))
                        else:
                            rows_found += 1
                            self.stdout.write(f"Rule already exists for {code} under {commodity} / {scope}")
                            if rule.trigger_mode != CommodityChargeRule.TRIGGER_MODE_AUTO:
                                rule.trigger_mode = CommodityChargeRule.TRIGGER_MODE_AUTO
                                rule.save(update_fields=['trigger_mode'])
                                self.stdout.write(self.style.WARNING(f"  -> Updated trigger_mode to AUTO for {code} / {scope}"))

        self.stdout.write(self.style.SUCCESS(f"\nCompleted. Rows found: {rows_found}. Rows created: {rows_created}."))
