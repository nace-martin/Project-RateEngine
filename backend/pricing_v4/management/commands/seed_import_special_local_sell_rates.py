from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.management.commands._sell_seed_utils import seed_import_sell_rate
from pricing_v4.models import ProductCode


@dataclass(frozen=True)
class CommodityRate:
    code: str
    pgk_collect: str
    aud_prepaid: str
    usd_prepaid: str


RATES = (
    # Launch assumptions:
    # - PGK values align with existing PNG local special-handling fees.
    # - AUD/USD values mirror the current export FCY DG pattern and keep
    #   import special local handling commercially usable until final tariffs arrive.
    CommodityRate(code="IMP-DG-SPECIAL", pgk_collect="250.00", aud_prepaid="100.00", usd_prepaid="80.00"),
    CommodityRate(code="IMP-AVI-SPECIAL", pgk_collect="100.00", aud_prepaid="60.00", usd_prepaid="50.00"),
    CommodityRate(code="IMP-HVC-SPECIAL", pgk_collect="100.00", aud_prepaid="60.00", usd_prepaid="50.00"),
)


class Command(BaseCommand):
    help = "Seed import destination-local special commodity sell tariffs into LocalSellRate"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Seed rates for the given year (default: current year).",
        )
        parser.add_argument(
            "--location",
            default="POM",
            help="Destination station code for the import local tariffs (default: POM).",
        )

    def handle(self, *args, **options):
        year = options["year"]
        location = str(options["location"] or "POM").strip().upper()
        valid_from = date(year, 1, 1)
        valid_until = date(year, 12, 31)

        self.stdout.write("=" * 72)
        self.stdout.write(f"Seeding Import Special Local Sell Rates for {location} ({year})")
        self.stdout.write("=" * 72)

        created = 0
        updated = 0

        with transaction.atomic():
            for rate in RATES:
                product_code = ProductCode.objects.get(code=rate.code)

                for payment_term, currency, amount in (
                    ("COLLECT", "PGK", rate.pgk_collect),
                    ("PREPAID", "AUD", rate.aud_prepaid),
                    ("PREPAID", "USD", rate.usd_prepaid),
                ):
                    result = seed_import_sell_rate(
                        product_code=product_code,
                        origin_airport="ANY",
                        destination_airport=location,
                        currency=currency,
                        valid_from=valid_from,
                        valid_until=valid_until,
                        rate_per_shipment=Decimal(amount),
                        payment_term=payment_term,
                    )
                    if result.created:
                        created += 1
                    else:
                        updated += 1
                    self.stdout.write(
                        f"  {('Created' if result.created else 'Updated')}: "
                        f"{product_code.code} {payment_term} {currency} {amount}"
                    )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Local special tariffs ready. Created={created}, Updated={updated}"))
