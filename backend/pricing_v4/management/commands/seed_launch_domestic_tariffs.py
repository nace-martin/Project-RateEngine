from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pricing_v4.models import Agent, DomesticCOGS, DomesticSellRate, ProductCode, Surcharge


@dataclass(frozen=True)
class RouteRate:
    origin: str
    destination: str
    rate_per_kg: str


COGS_ROUTE_RATES: tuple[RouteRate, ...] = (
    RouteRate("POM", "GUR", "7.85"),
    RouteRate("POM", "BUA", "19.35"),
    RouteRate("POM", "DAU", "11.05"),
    RouteRate("POM", "GKA", "8.30"),
    RouteRate("POM", "HKN", "11.55"),
    RouteRate("POM", "KVG", "17.65"),
    RouteRate("POM", "KIE", "20.45"),
    RouteRate("POM", "KOM", "14.00"),
    RouteRate("POM", "UNG", "16.05"),
    RouteRate("POM", "CMU", "7.20"),
    RouteRate("POM", "LAE", "6.10"),
    RouteRate("POM", "LNV", "18.75"),
    RouteRate("POM", "LSA", "8.00"),
    RouteRate("POM", "MAG", "8.75"),
    RouteRate("POM", "MAS", "13.25"),
    RouteRate("POM", "MDU", "9.50"),
    RouteRate("POM", "HGU", "8.85"),
    RouteRate("POM", "PNP", "4.85"),
    RouteRate("POM", "RAB", "15.45"),
    RouteRate("POM", "TBG", "16.05"),
    RouteRate("POM", "TIZ", "14.00"),
    RouteRate("POM", "TFI", "5.25"),
    RouteRate("POM", "VAI", "17.15"),
    RouteRate("POM", "WBM", "6.65"),
    RouteRate("POM", "WWK", "13.75"),
    RouteRate("LAE", "GUR", "9.95"),
    RouteRate("LAE", "BUA", "13.85"),
    RouteRate("LAE", "DAU", "9.95"),
    RouteRate("LAE", "GKA", "9.95"),
    RouteRate("LAE", "HKN", "11.05"),
    RouteRate("LAE", "KVG", "12.75"),
    RouteRate("LAE", "KIE", "15.45"),
    RouteRate("LAE", "UNG", "16.05"),
    RouteRate("LAE", "CMU", "9.95"),
    RouteRate("LAE", "LNV", "14.95"),
    RouteRate("LAE", "MAG", "9.95"),
    RouteRate("LAE", "MAS", "8.25"),
    RouteRate("LAE", "MDU", "11.05"),
    RouteRate("LAE", "HGU", "9.95"),
    RouteRate("LAE", "PNP", "8.25"),
    RouteRate("LAE", "POM", "6.10"),
    RouteRate("LAE", "RAB", "11.60"),
    RouteRate("LAE", "TBG", "17.15"),
    RouteRate("LAE", "TIZ", "13.85"),
    RouteRate("LAE", "VAI", "15.45"),
    RouteRate("LAE", "WBM", "11.05"),
    RouteRate("LAE", "WWK", "12.10"),
)

SELL_ROUTE_RATES: tuple[RouteRate, ...] = (
    RouteRate("POM", "GUR", "9.15"),
    RouteRate("POM", "BUA", "22.45"),
    RouteRate("POM", "DAU", "12.85"),
    RouteRate("POM", "GKA", "9.65"),
    RouteRate("POM", "HKN", "13.40"),
    RouteRate("POM", "KVG", "20.50"),
    RouteRate("POM", "KIE", "23.75"),
    RouteRate("POM", "KOM", "16.25"),
    RouteRate("POM", "UNG", "18.65"),
    RouteRate("POM", "CMU", "8.40"),
    RouteRate("POM", "LAE", "7.30"),
    RouteRate("POM", "LNV", "21.75"),
    RouteRate("POM", "LSA", "9.30"),
    RouteRate("POM", "MAG", "10.15"),
    RouteRate("POM", "MAS", "15.40"),
    RouteRate("POM", "MDU", "11.05"),
    RouteRate("POM", "HGU", "10.30"),
    RouteRate("POM", "PNP", "5.65"),
    RouteRate("POM", "RAB", "17.95"),
    RouteRate("POM", "TBG", "18.65"),
    RouteRate("POM", "TIZ", "16.25"),
    RouteRate("POM", "TFI", "6.10"),
    RouteRate("POM", "VAI", "19.90"),
    RouteRate("POM", "WBM", "7.75"),
    RouteRate("POM", "WWK", "15.95"),
    RouteRate("LAE", "GUR", "11.55"),
    RouteRate("LAE", "BUA", "16.10"),
    RouteRate("LAE", "DAU", "11.55"),
    RouteRate("LAE", "GKA", "11.55"),
    RouteRate("LAE", "HKN", "12.85"),
    RouteRate("LAE", "KVG", "14.80"),
    RouteRate("LAE", "KIE", "17.95"),
    RouteRate("LAE", "UNG", "18.65"),
    RouteRate("LAE", "CMU", "11.55"),
    RouteRate("LAE", "LNV", "17.35"),
    RouteRate("LAE", "MAG", "11.55"),
    RouteRate("LAE", "MAS", "9.60"),
    RouteRate("LAE", "MDU", "12.85"),
    RouteRate("LAE", "HGU", "11.55"),
    RouteRate("LAE", "PNP", "9.60"),
    RouteRate("LAE", "POM", "7.10"),
    RouteRate("LAE", "RAB", "13.50"),
    RouteRate("LAE", "TBG", "19.90"),
    RouteRate("LAE", "TIZ", "16.10"),
    RouteRate("LAE", "VAI", "17.95"),
    RouteRate("LAE", "WBM", "12.85"),
    RouteRate("LAE", "WWK", "14.05"),
)

COGS_SURCHARGES = (
    ("DOM-DOC", "FLAT", "35.00", None),
    ("DOM-TERMINAL", "FLAT", "35.00", None),
    ("DOM-SECURITY", "PER_KG", "0.20", "5.00"),
    ("DOM-FSC", "PER_KG", "0.25", None),
)

SELL_SURCHARGES = (
    ("DOM-AWB", "FLAT", "70.00", None),
    ("DOM-SECURITY", "PER_KG", "0.20", "5.00"),
    ("DOM-FSC", "PER_KG", "0.35", None),
    ("DOM-DG-HANDLING", "FLAT", "195.00", None),
)


# Uplift percentages applied on top of the base freight line.
# Example: "200% of normal rate" = base freight + 100% uplift.
SPECIAL_UPLIFTS = (
    ("DOM-EXPRESS", "100.00"),
    ("DOM-VALUABLE", "400.00"),
    ("DOM-LIVE-ANIMAL", "100.00"),
    ("DOM-OVERSIZE", "50.00"),
)


class Command(BaseCommand):
    help = (
        "Seed launch domestic air tariffs from the current tariff sheets. "
        "COGS uses the original buy-rate sheet. SELL uses the corrected POM/LAE commercial sheet."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Seed rates for the given year (default: current year).",
        )

    def handle(self, *args, **options):
        year = options["year"]
        valid_from = date(year, 1, 1)
        valid_until = date(year, 12, 31)

        freight_pc = self._get_product_code("DOM-FRT-AIR")
        self._get_product_code("DOM-DOC")
        self._get_product_code("DOM-TERMINAL")
        self._get_product_code("DOM-AWB")
        self._get_product_code("DOM-SECURITY")
        self._get_product_code("DOM-FSC")
        self._get_product_code("DOM-DG-HANDLING")
        self._get_product_code("DOM-EXPRESS")
        self._get_product_code("DOM-VALUABLE")
        self._get_product_code("DOM-LIVE-ANIMAL")
        self._get_product_code("DOM-OVERSIZE")

        px_agent, _ = Agent.objects.get_or_create(
            code="PX-DOM",
            defaults={
                "name": "Air Niugini (Domestic)",
                "agent_type": "CARRIER",
                "country_code": "PG",
            },
        )

        self.stdout.write("=" * 72)
        self.stdout.write(f"Seeding Launch Domestic Tariffs ({year})")
        self.stdout.write("=" * 72)

        cogs_freight_created = cogs_freight_updated = 0
        sell_freight_created = sell_freight_updated = 0
        cogs_surcharge_created = cogs_surcharge_updated = 0
        sell_surcharge_created = sell_surcharge_updated = 0
        legacy_surcharges_disabled = 0

        with transaction.atomic():
            for route in COGS_ROUTE_RATES:
                rate = Decimal(route.rate_per_kg)
                _, cogs_created = DomesticCOGS.objects.update_or_create(
                    product_code=freight_pc,
                    origin_zone=route.origin,
                    destination_zone=route.destination,
                    agent=px_agent,
                    valid_from=valid_from,
                    defaults={
                        "currency": "PGK",
                        "rate_per_kg": rate,
                        "rate_per_shipment": None,
                        "min_charge": None,
                        "max_charge": None,
                        "valid_until": valid_until,
                    },
                )
                cogs_freight_created += int(cogs_created)
                cogs_freight_updated += int(not cogs_created)
                self.stdout.write(
                    f"  COGS Freight {route.origin}->{route.destination}: K{route.rate_per_kg}/kg"
                )

            for route in SELL_ROUTE_RATES:
                rate = Decimal(route.rate_per_kg)
                _, sell_created = DomesticSellRate.objects.update_or_create(
                    product_code=freight_pc,
                    origin_zone=route.origin,
                    destination_zone=route.destination,
                    valid_from=valid_from,
                    defaults={
                        "currency": "PGK",
                        "rate_per_kg": rate,
                        "rate_per_shipment": None,
                        "min_charge": None,
                        "max_charge": None,
                        "percent_rate": None,
                        "valid_until": valid_until,
                    },
                )
                sell_freight_created += int(sell_created)
                sell_freight_updated += int(not sell_created)
                self.stdout.write(
                    f"  SELL Freight {route.origin}->{route.destination}: K{route.rate_per_kg}/kg"
                )

            created_count, updated_count = self._seed_global_surcharges(
                rate_side="COGS",
                valid_from=valid_from,
                valid_until=valid_until,
            )
            cogs_surcharge_created += created_count
            cogs_surcharge_updated += updated_count

            created_count, updated_count = self._seed_global_surcharges(
                rate_side="SELL",
                valid_from=valid_from,
                valid_until=valid_until,
            )
            sell_surcharge_created += created_count
            sell_surcharge_updated += updated_count

            for code in ("DOM-DOC", "DOM-TERMINAL"):
                pc = ProductCode.objects.filter(code=code).first()
                if pc:
                    disabled = Surcharge.objects.filter(
                        product_code=pc,
                        service_type="DOMESTIC_AIR",
                        rate_side="SELL",
                    ).exclude(valid_from=valid_from).update(is_active=False, valid_until=valid_until)
                    legacy_surcharges_disabled += disabled
                    self.stdout.write(f"  Disabled SELL surcharge {code} in favour of DOM-AWB")

            legacy_surcharges_disabled += self._disable_overlapping_legacy_surcharges(
                rate_side="COGS",
                valid_from=valid_from,
                valid_until=valid_until,
            )
            legacy_surcharges_disabled += self._disable_overlapping_legacy_surcharges(
                rate_side="SELL",
                valid_from=valid_from,
                valid_until=valid_until,
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Domestic launch tariffs ready. "
                f"COGS freight created/updated={cogs_freight_created}/{cogs_freight_updated}; "
                f"SELL freight created/updated={sell_freight_created}/{sell_freight_updated}; "
                f"COGS surcharges created/updated={cogs_surcharge_created}/{cogs_surcharge_updated}; "
                f"SELL surcharges created/updated={sell_surcharge_created}/{sell_surcharge_updated}; "
                f"legacy surcharges disabled={legacy_surcharges_disabled}"
            )
        )

    def _seed_global_surcharges(self, *, rate_side: str, valid_from: date, valid_until: date) -> tuple[int, int]:
        created = 0
        updated = 0

        surcharge_set = COGS_SURCHARGES if rate_side == "COGS" else SELL_SURCHARGES

        for code, rate_type, amount, min_charge in surcharge_set:
            pc = self._get_product_code(code)
            _, was_created = Surcharge.objects.update_or_create(
                product_code=pc,
                service_type="DOMESTIC_AIR",
                rate_side=rate_side,
                valid_from=valid_from,
                defaults={
                    "rate_type": rate_type,
                    "amount": Decimal(amount),
                    "min_charge": Decimal(min_charge) if min_charge else None,
                    "max_charge": None,
                    "currency": "PGK",
                    "valid_until": valid_until,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        for code, uplift_percent in SPECIAL_UPLIFTS:
            pc = self._get_product_code(code)
            _, was_created = Surcharge.objects.update_or_create(
                product_code=pc,
                service_type="DOMESTIC_AIR",
                rate_side=rate_side,
                valid_from=valid_from,
                defaults={
                    "rate_type": "PERCENT",
                    "amount": Decimal(uplift_percent),
                    "min_charge": None,
                    "max_charge": None,
                    "currency": "PGK",
                    "valid_until": valid_until,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        return created, updated

    def _disable_overlapping_legacy_surcharges(
        self,
        *,
        rate_side: str,
        valid_from: date,
        valid_until: date,
    ) -> int:
        disabled = 0
        surcharge_set = COGS_SURCHARGES if rate_side == "COGS" else SELL_SURCHARGES
        relevant_codes = [code for code, *_ in surcharge_set] + [code for code, _ in SPECIAL_UPLIFTS]

        for code in relevant_codes:
            pc = ProductCode.objects.filter(code=code).first()
            if not pc:
                continue
            updated = Surcharge.objects.filter(
                product_code=pc,
                service_type="DOMESTIC_AIR",
                rate_side=rate_side,
                is_active=True,
                valid_from__lt=valid_from,
                valid_until__gte=valid_from,
            ).update(is_active=False, valid_until=valid_until)
            disabled += updated
        return disabled

    def _get_product_code(self, code: str) -> ProductCode:
        product_code = ProductCode.objects.filter(code=code).first()
        if not product_code:
            raise CommandError(
                f"Required ProductCode '{code}' not found. Run seed_domestic_product_codes first."
            )
        return product_code
