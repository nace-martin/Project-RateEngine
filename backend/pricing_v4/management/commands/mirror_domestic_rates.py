from django.core.management.base import BaseCommand
from django.db import transaction
from pricing_v4.models import DomesticCOGS, DomesticSellRate, ProductCode, Agent

class Command(BaseCommand):
    help = 'Mirrors ex-POM rates to create to-POM rates (symmetrical pricing)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 60)
        self.stdout.write("Mirroring Domestic Rates (Creating TO-POM routes)")
        self.stdout.write("=" * 60)

        with transaction.atomic():
            # 1. Mirror COGS
            cogs_count = 0
            ex_pom_cogs = DomesticCOGS.objects.filter(origin_zone='POM')
            
            for cogs in ex_pom_cogs:
                # Swap origin/dest
                new_origin = cogs.destination_zone
                new_dest = cogs.origin_zone
                
                DomesticCOGS.objects.update_or_create(
                    product_code=cogs.product_code,
                    origin_zone=new_origin,
                    destination_zone=new_dest,
                    carrier=cogs.carrier,
                    agent=cogs.agent,
                    valid_from=cogs.valid_from,
                    defaults={
                        'currency': cogs.currency,
                        'rate_per_kg': cogs.rate_per_kg,
                        'rate_per_shipment': cogs.rate_per_shipment,
                        'min_charge': cogs.min_charge,
                        'valid_until': cogs.valid_until
                    }
                )
                cogs_count += 1
                
            self.stdout.write(f"Mirrored {cogs_count} COGS records")

            # 2. Mirror Sell Rates
            sell_count = 0
            ex_pom_sell = DomesticSellRate.objects.filter(origin_zone='POM')
            
            for sell in ex_pom_sell:
                new_origin = sell.destination_zone
                new_dest = sell.origin_zone
                
                DomesticSellRate.objects.update_or_create(
                    product_code=sell.product_code,
                    origin_zone=new_origin,
                    destination_zone=new_dest,
                    valid_from=sell.valid_from,
                    defaults={
                        'currency': sell.currency,
                        'rate_per_kg': sell.rate_per_kg,
                        'rate_per_shipment': sell.rate_per_shipment,
                        'min_charge': sell.min_charge,
                        'percent_rate': sell.percent_rate,
                        'valid_until': sell.valid_until
                    }
                )
                sell_count += 1
                
            self.stdout.write(f"Mirrored {sell_count} Sell Rate records")
