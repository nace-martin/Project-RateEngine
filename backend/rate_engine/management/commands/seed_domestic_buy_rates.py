# backend/rate_engine/management/commands/seed_domestic_buy_rates.py

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from rate_engine.models import (
    Providers,
    Stations,
    Ratecards,
    RatecardConfig,
    Lanes,
    LaneBreaks,
    FeeTypes,
    RatecardFees,
    Services,
    ServiceItems,
    SellCostLinksSimple,
)

# Domestic Air Freight Rates (in PGK per KG)
# All rates are Airport-to-Airport
DOMESTIC_RATES = {
    "POM": {
        "LAE": "2.50", "HGU": "3.50", "MAG": "4.00", "WWK": "4.50",
        "RAB": "5.00", "HKN": "5.50",
    },
    "LAE": {
        "POM": "2.50", "HGU": "2.00", "MAG": "2.50", "WWK": "3.00",
        "RAB": "3.50", "HKN": "4.00",
    },
}

class Command(BaseCommand):
    help = "Seeds the database with initial domestic BUY rate data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding domestic BUY rate data...")

        # 1. Get or Create the Provider for Domestic Rates (e.g., a local carrier)
        provider, _ = Providers.objects.get_or_create(
            name="PNG Domestic Carrier",
            defaults={"provider_type": "CARRIER"},
        )

        # 2. Define and Create the Domestic BUY Rate Card
        ratecard, created = Ratecards.objects.update_or_create(
            name="PNG Domestic BUY Rates (Flat per KG)",
            defaults={
                "provider": provider,
                "role": "BUY",
                "scope": "DOMESTIC",
                "direction": "DOMESTIC",
                "rate_strategy": "FLAT_PER_KG",
                "currency": "PGK",
                "source": "SEED",
                "status": "PUBLISHED",
                "effective_date": now().date(),
                "notes": None,
                "meta": {
                    "d2d_available_between": ["POM-LAE", "LAE-POM"],
                    "special_multipliers": {
                        "EXPRESS": 2.0,
                        "VALUABLE": 5.0,
                        "LIVE_ANIMAL": 2.0,
                        "OVERSIZE_250KG": 1.5,
                    },
                },
                "created_at": now(),
                "updated_at": now(),
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Ratecard: "{ratecard.name}"'))
        else:
            self.stdout.write(f'Ratecard "{ratecard.name}" already exists.')

        # 3. Configure the Rate Card to use the correct dimensional factor
        RatecardConfig.objects.update_or_create(
            ratecard=ratecard,
            defaults={
                "dim_factor_kg_per_m3": Decimal("167.00"),  # Standard 1:6000
                "rate_strategy": "FLAT_PER_KG",
                "created_at": now(),
            }
        )

        # 4. Create Lanes and the single "FLAT" break for each route
        stations = {s.iata: s for s in Stations.objects.all()}
        for origin_iata, destinations in DOMESTIC_RATES.items():
            for dest_iata, rate_per_kg in destinations.items():
                if origin_iata not in stations or dest_iata not in stations:
                    self.stdout.write(self.style.WARNING(f"Skipping {origin_iata}-{dest_iata}: Station not found."))
                    continue

                lane, _ = Lanes.objects.update_or_create(
                    ratecard=ratecard,
                    origin=stations[origin_iata],
                    dest=stations[dest_iata],
                    defaults={
                        "airline": None,
                        "is_direct": True,
                        "via": None,
                    }
                )

                LaneBreaks.objects.update_or_create(
                    lane=lane,
                    break_code="FLAT",
                    defaults={"per_kg": Decimal(rate_per_kg)}
                )
        self.stdout.write(self.style.SUCCESS("Successfully created domestic lanes and flat rate breaks."))


        # 5. Define and Create Domestic Surcharges (Fee Types and Fees)
        fee_types_data = [
            {"code": "DOC", "description": "Documentation Fee", "basis": "PER_SHIPMENT"},
            {"code": "TERM", "description": "Terminal Fee", "basis": "PER_SHIPMENT"},
            {"code": "SEC", "description": "Security Surcharge", "basis": "PER_KG"},
            {"code": "FUEL", "description": "Fuel Surcharge", "basis": "PER_KG"},
        ]
        for ft_data in fee_types_data:
            FeeTypes.objects.get_or_create(
                code=ft_data["code"],
                defaults={
                    "description": ft_data["description"],
                    "basis": ft_data["basis"],
                    "default_tax_pct": Decimal("10.00"),
                },
            )

        fees_data = [
            {"code": "DOC", "amount": "35.00"},
            {"code": "TERM", "amount": "35.00"},
            {"code": "SEC", "amount": "0.20", "min_amount": "5.00"},
            {"code": "FUEL", "amount": "0.25"},
        ]

        for fee_data in fees_data:
            fee_type = FeeTypes.objects.get(code=fee_data["code"])
            RatecardFees.objects.update_or_create(
                ratecard=ratecard,
                fee_type=fee_type,
                defaults={
                    "amount": Decimal(fee_data["amount"]),
                    "min_amount": Decimal(fee_data["min_amount"]) if "min_amount" in fee_data else None,
                    "currency": "PGK",
                    "applies_if": {},
                    "created_at": now(),
                }
            )
        self.stdout.write(self.style.SUCCESS("Successfully created domestic surcharges."))

        # 6. Create a simple DOMESTIC SELL menu linked to BUY costs (pass-through)
        sell_card, _ = Ratecards.objects.update_or_create(
            name="PGK Domestic SELL Menu",
            defaults={
                "provider": provider,
                "role": "SELL",
                "scope": "DOMESTIC",
                "direction": "DOMESTIC",
                "audience": "PGK_LOCAL",
                "currency": "PGK",
                "source": "SEED",
                "status": "PUBLISHED",
                "effective_date": now().date(),
                "meta": {},
                "created_at": now(),
                "updated_at": now(),
            },
        )

        # Ensure services exist
        svc_specs = [
            ("AIR_FREIGHT", "Air Freight Charge", "PER_KG"),
            ("DOC", "Documentation Fee", "PER_SHIPMENT"),
            ("TERM", "Terminal Fee", "PER_SHIPMENT"),
            ("SEC", "Security Surcharge", "PER_KG"),
            ("FUEL", "Fuel Surcharge", "PER_KG"),
        ]
        svc_map = {}
        for code, name, basis in svc_specs:
            svc, _ = Services.objects.get_or_create(code=code, defaults={"name": name, "basis": basis})
            svc_map[code] = svc

        # Create service items on SELL card
        item_map = {}
        for code, name, basis in svc_specs:
            item, _ = ServiceItems.objects.update_or_create(
                ratecard=sell_card,
                service=svc_map[code],
                defaults={
                    "currency": "PGK",
                    "amount": None,  # price set by mapping
                    # Apply 10% GST on domestic SELL items
                    "tax_pct": Decimal("10.00"),
                    "conditions_json": {},
                },
            )
            item_map[code] = item

        # Ensure a fee type exists for base freight to support mapping
        FeeTypes.objects.get_or_create(
            code="FREIGHT",
            defaults={
                "description": "Base Air Freight",
                "basis": "PER_KG",
                "default_tax_pct": Decimal("0.00"),
            },
        )

        # Create mapping links: pass-through from BUY context to SELL items
        def link(sell_code, buy_code, mapping_type="PASS_THROUGH"):
            ft = FeeTypes.objects.get(code=buy_code)
            SellCostLinksSimple.objects.update_or_create(
                sell_item=item_map[sell_code],
                buy_fee_code=ft,
                defaults={"mapping_type": mapping_type, "mapping_value": None},
            )

        link("AIR_FREIGHT", "FREIGHT")
        link("DOC", "DOC")
        link("TERM", "TERM")
        link("SEC", "SEC")
        link("FUEL", "FUEL")

        self.stdout.write(self.style.SUCCESS("Domestic SELL menu created with pass-through mappings."))
        self.stdout.write(self.style.SUCCESS("Domestic BUY/SELL rate seeding complete."))
