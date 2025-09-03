# backend/rate_engine/management/commands/seed_domestic_buy_rates.py

import json
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

# Updated with the full list of actual domestic BUY rates
DOMESTIC_RATES = {
    "POM": {
        "GUR": "7.85", "BUA": "19.35", "DAU": "11.05", "GKA": "8.30",
        "HKN": "11.55", "KVG": "17.65", "KIE": "20.45", "KOM": "14.00",
        "UNG": "16.05", "CMU": "7.20", "LAE": "6.10", "LNV": "18.75",
        "LSA": "8.00", "MAG": "8.75", "MAS": "13.25", "MDU": "9.50",
        "HGU": "8.85", "PNP": "4.85", "RAB": "15.45", "TBG": "16.05",
        "TIZ": "14.00", "TFI": "5.25", "VAI": "17.15", "WBM": "6.65",
        "WWK": "13.75",
    },
    "LAE": {
        "GUR": "9.95", "BUA": "13.85", "DAU": "9.95", "GKA": "9.95",
        "HKN": "11.05", "KVG": "12.75", "KIE": "15.45", "UNG": "16.05",
        "CMU": "9.95", "LNV": "14.95", "MAG": "9.95", "MAS": "8.25",
        "MDU": "11.05", "HGU": "9.95", "PNP": "8.25", "POM": "6.10",
        "RAB": "11.60", "TBG": "17.15", "TIZ": "13.85", "VAI": "15.45",
        "WBM": "11.05", "WWK": "12.10",
    },
    "HGU": {
        "GUR": "10.50", "BUA": "17.15", "DAU": "9.40", "GKA": "11.05",
        "HKN": "12.15", "KVG": "14.95", "UNG": "18.25", "CMU": "11.05",
        "LAE": "9.95", "LNV": "16.55", "MAG": "11.05", "MAS": "14.35",
        "MDU": "12.15", "PNP": "8.85", "POM": "8.85", "RAB": "14.95",
        "TBG": "5.55", "TIZ": "13.25", "VAI": "16.55", "WBM": "13.25",
        "WWK": "6.10",
    },
    "GKA": {
        "GUR": "10.50", "BUA": "16.05", "DAU": "11.05", "HKN": "11.60",
        "KVG": "14.35", "UNG": "17.65", "CMU": "11.05", "LAE": "9.95",
        "LNV": "16.55", "MAG": "11.05", "MAS": "13.85", "MDU": "12.15",
        "HGU": "11.05", "PNP": "8.85", "POM": "8.30", "RAB": "14.35",
        "TBG": "18.25", "TIZ": "13.25", "VAI": "16.05", "WBM": "12.75",
        "WWK": "13.25",
    },
    "RAB": {
        "GUR": "13.25", "BUA": "5.55", "DAU": "21.55", "GKA": "14.35",
        "HKN": "5.00", "KVG": "5.55", "KIE": "7.75", "UNG": "16.55",
        "CMU": "13.85", "LAE": "11.60", "LNV": "5.00", "MAG": "12.75",
        "MAS": "14.95", "MDU": "14.95", "HGU": "14.95", "PNP": "11.05",
        "POM": "15.45", "TBG": "20.95", "TIZ": "16.55", "VAI": "18.25",
        "WBM": "15.45", "WWK": "16.05",
    },
    "GUR": {
        "BUA": "15.45", "DAU": "15.45", "GKA": "10.50", "HKN": "11.60",
        "KVG": "13.25", "KIE": "16.05", "UNG": "16.55", "CMU": "11.05",
        "LAE": "9.95", "LNV": "16.05", "MAG": "11.05", "MAS": "13.80",
        "MDU": "11.60", "HGU": "10.50", "PNP": "8.80", "POM": "7.85",
        "RAB": "13.25", "TBG": "17.65", "TIZ": "12.71", "VAI": "15.45",
        "WBM": "11.60", "WWK": "13.80",
    },
    "BUA": {
        "GUR": "15.45", "GKA": "16.05", "HKN": "15.45", "KVG": "8.85",
        "KIE": "5.15", "CMU": "16.65", "LAE": "13.85", "LNV": "11.60",
        "MAG": "14.95", "MAS": "12.15", "MDU": "17.65", "HGU": "17.15",
        "PNP": "13.25", "POM": "19.35", "RAB": "5.55", "TBG": "23.75",
        "TIZ": "18.25", "VAI": "18.25", "WBM": "12.75", "WWK": "18.25",
    },
    "DAU": {
        "GUR": "15.45", "GKA": "11.05", "HKN": "17.15", "KVG": "13.25",
        "UNG": "8.95", "LAE": "9.95", "LNV": "13.25", "MAG": "11.05",
        "MDU": "9.95", "HGU": "9.40", "PNP": "11.05", "POM": "11.05",
        "RAB": "21.55", "TIZ": "11.05", "VAI": "12.75", "WBM": "10.50",
        "WWK": "12.75",
    },
    "HKN": {
        "GUR": "11.60", "BUA": "15.45", "DAU": "17.15", "GKA": "11.60",
        "KVG": "14.35", "KIE": "17.65", "UNG": "18.25", "CMU": "11.60",
        "LAE": "11.05", "LNV": "17.15", "MAG": "11.60", "MAS": "14.90",
        "MDU": "12.75", "HGU": "12.15", "PNP": "9.95", "POM": "11.55",
        "RAB": "5.00", "TBG": "18.75", "TIZ": "15.45", "VAI": "17.15",
        "WBM": "13.25", "WWK": "14.35",
    },
    "KVG": {
        "GUR": "13.25", "BUA": "8.85", "DAU": "13.25", "GKA": "14.35",
        "HKN": "14.35", "KIE": "11.05", "UNG": "17.15", "CMU": "14.35",
        "LAE": "12.75", "LNV": "8.30", "MAG": "13.25", "MAS": "6.10",
        "MDU": "15.45", "HGU": "14.95", "PNP": "11.60", "POM": "17.65",
        "RAB": "5.55", "TBG": "22.05", "TIZ": "16.55", "VAI": "19.85",
        "WBM": "16.05", "WWK": "16.05",
    },
    "KIE": {"GUR": "16.05", "BUA": "5.15", "HKN": "17.65", "KVG": "11.05", "LAE": "15.45", "POM": "20.45", "RAB": "7.75"},
    "KOM": {"POM": "14.00"},
    "UNG": {
        "GUR": "16.55", "DAU": "8.95", "GKA": "17.65", "HKN": "18.25", "KVG": "17.15",
        "CMU": "16.55", "LAE": "16.05", "LNV": "22.05", "MAG": "17.65", "HGU": "18.25",
        "PNP": "11.05", "POM": "16.05", "RAB": "16.55", "TBG": "5.55", "WWK": "19.85",
    },
    "CMU": {
        "GUR": "11.05", "BUA": "16.65", "GKA": "11.05", "HKN": "11.60", "KVG": "14.35",
        "UNG": "16.55", "LAE": "9.95", "LNV": "16.55", "MAG": "11.05", "MAS": "14.35",
        "MDU": "12.15", "HGU": "11.05", "PNP": "8.85", "POM": "7.20", "RAB": "13.85",
        "TBG": "18.25", "TIZ": "12.75", "VAI": "14.35", "WBM": "12.15", "WWK": "13.25",
    },
    "LNV": {
        "GUR": "16.05", "BUA": "11.60", "DAU": "13.25", "GKA": "16.55", "HKN": "17.15",
        "KVG": "8.30", "UNG": "22.05", "CMU": "16.55", "LAE": "14.95", "MAG": "16.55",
        "MAS": "19.35", "MDU": "17.65", "HGU": "16.55", "PNP": "13.25", "POM": "18.75",
        "RAB": "5.00", "TBG": "24.26", "TIZ": "18.75", "VAI": "21.55", "WBM": "18.25",
        "WWK": "18.75",
    },
    "LSA": {"POM": "8.00"},
    "MAG": {
        "GUR": "11.05", "BUA": "14.95", "DAU": "11.05", "GKA": "11.05", "HKN": "11.60",
        "KVG": "13.25", "UNG": "17.65", "CMU": "11.05", "LAE": "9.95", "LNV": "16.55",
        "MAS": "7.20", "MDU": "12.15", "HGU": "11.05", "PNP": "8.85", "POM": "8.75",
        "RAB": "12.75", "TBG": "18.75", "TIZ": "14.35", "VAI": "6.65", "WBM": "12.75",
        "WWK": "5.55",
    },
    "MAS": {
        "GUR": "13.80", "BUA": "12.15", "GKA": "13.85", "HKN": "14.90", "KVG": "6.10",
        "CMU": "14.35", "LAE": "8.25", "LNV": "19.35", "MAG": "7.20", "MDU": "14.95",
        "HGU": "14.35", "PNP": "12.15", "POM": "13.25", "RAB": "14.95", "TBG": "21.55",
        "TIZ": "16.05", "VAI": "9.40", "WBM": "15.45", "WWK": "16.55",
    },
    "MDU": {
        "GUR": "11.60", "BUA": "17.65", "DAU": "9.95", "GKA": "12.15", "HKN": "12.75",
        "KVG": "15.45", "CMU": "12.15", "LAE": "11.05", "LNV": "17.65", "MAG": "12.15",
        "MAS": "14.95", "HGU": "12.15", "PNP": "9.40", "POM": "9.50", "RAB": "14.95",
        "TBG": "19.35", "TIZ": "3.35", "VAI": "17.15", "WBM": "14.35", "WWK": "14.95",
    },
    "PNP": {
        "GUR": "8.80", "BUA": "13.25", "DAU": "11.05", "GKA": "8.85", "HKN": "9.95",
        "KVG": "11.60", "UNG": "11.05", "CMU": "8.85", "LAE": "8.25", "LNV": "13.25",
        "MAG": "8.85", "MAS": "12.15", "MDU": "9.40", "HGU": "8.85", "POM": "4.85",
        "RAB": "11.05", "TBG": "15.45", "TIZ": "12.15", "TFI": "2.40", "VAI": "13.25",
        "WBM": "9.40", "WWK": "11.05",
    },
    "TBG": {
        "GUR": "17.65", "BUA": "23.75", "GKA": "18.25", "HKN": "18.75", "KVG": "22.05",
        "UNG": "5.55", "CMU": "18.25", "LAE": "17.15", "LNV": "24.26", "MAG": "18.75",
        "MAS": "21.55", "MDU": "19.35", "HGU": "5.55", "PNP": "15.45", "POM": "16.05",
        "RAB": "20.95", "TIZ": "20.45", "VAI": "22.65", "WBM": "19.85", "WWK": "20.95",
    },
    "TIZ": {
        "GUR": "12.71", "BUA": "18.25", "DAU": "11.05", "GKA": "13.25", "HKN": "15.45",
        "KVG": "16.55", "CMU": "12.75", "LAE": "13.85", "LNV": "18.75", "MAG": "14.35",
        "MAS": "16.05", "MDU": "3.35", "HGU": "13.25", "PNP": "12.15", "POM": "14.00",
        "RAB": "16.55", "TBG": "20.45", "VAI": "18.25", "WBM": "14.35", "WWK": "16.55",
    },
    "TFI": {"PNP": "2.40", "POM": "5.25"},
    "VAI": {
        "GUR": "15.45", "BUA": "18.25", "DAU": "12.75", "GKA": "16.05", "HKN": "17.15",
        "KVG": "19.85", "CMU": "14.35", "LAE": "15.45", "LNV": "21.55", "MAG": "6.65",
        "MAS": "9.40", "MDU": "17.15", "HGU": "16.55", "PNP": "13.25", "POM": "17.15",
        "RAB": "18.25", "TBG": "22.65", "TIZ": "18.25", "WBM": "17.65", "WWK": "5.55",
    },
    "WBM": {
        "GUR": "11.60", "BUA": "12.75", "DAU": "10.50", "GKA": "12.75", "HKN": "13.25",
        "KVG": "16.05", "CMU": "12.15", "LAE": "11.05", "LNV": "18.25", "MAG": "12.75",
        "MAS": "15.45", "MDU": "14.35", "HGU": "13.25", "PNP": "9.40", "POM": "6.65",
        "RAB": "15.45", "TBG": "19.85", "TIZ": "14.35", "VAI": "17.65", "WWK": "15.45",
    },
    "WWK": {
        "GUR": "13.80", "BUA": "18.25", "DAU": "12.75", "GKA": "13.25", "HKN": "14.35",
        "KVG": "16.05", "UNG": "19.85", "CMU": "13.25", "LAE": "12.10", "LNV": "18.75",
        "MAG": "5.55", "MAS": "16.55", "MDU": "14.95", "HGU": "6.10", "PNP": "11.05",
        "POM": "13.75", "RAB": "16.05", "TBG": "20.95", "TIZ": "16.55", "VAI": "5.55",
        "WBM": "15.45",
    },
}

# Curated station info for PNG domestic IATAs used above
STATION_INFO = {
    "POM": ("Port Moresby", "PG"),
    "LAE": ("Lae / Nadzab", "PG"),
    "GUR": ("Alotau / Gurney", "PG"),
    "BUA": ("Buka", "PG"),
    "DAU": ("Daru", "PG"),
    "GKA": ("Goroka", "PG"),
    "HKN": ("Hoskins (Kimbe)", "PG"),
    "KVG": ("Kavieng", "PG"),
    "KIE": ("Kieta / Aropa (Bougainville)", "PG"),
    "KOM": ("Komo (Hela)", "PG"),
    "UNG": ("Kiunga", "PG"),
    "CMU": ("Kundiawa (Chimbu)", "PG"),
    "LNV": ("Lihir Island", "PG"),
    "LSA": ("Losuia (Kiriwina)", "PG"),
    "MAG": ("Madang", "PG"),
    "MAS": ("Manus / Momote", "PG"),
    "MDU": ("Mendi", "PG"),
    "HGU": ("Mount Hagen", "PG"),
    "PNP": ("Popondetta / Girua", "PG"),
    "RAB": ("Rabaul / Tokua", "PG"),
    "TBG": ("Tabubil", "PG"),
    "TIZ": ("Tari", "PG"),
    "TFI": ("Tufi", "PG"),
    "VAI": ("Vanimo", "PG"),
    "WBM": ("Wapenamanda", "PG"),
    "WWK": ("Wewak / Boram", "PG"),
}

class Command(BaseCommand):
    help = "Seeds the database with initial domestic BUY and SELL rate data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding domestic BUY and SELL rate data with actuals...")

        # =================================================================
        # 1. SETUP BUY-SIDE (COSTS)
        # =================================================================
        provider, _ = Providers.objects.get_or_create(
            name="PNG Domestic Carrier",
            defaults={"provider_type": "CARRIER"},
        )

        rc_buy, _ = Ratecards.objects.update_or_create(
            provider=provider,
            name="PNG Domestic BUY Rates (Flat per KG)",
            effective_date=now().date(),
            defaults={
                "role": "BUY",
                "scope": "DOMESTIC",
                "direction": "DOMESTIC",
                "rate_strategy": "FLAT_PER_KG",
                "currency": "PGK",
                "status": "ACTIVE",
                "source": "SEEDER",
                "created_at": now(),
                "updated_at": now(),
                "meta": {"d2d_available_between": ["POM-LAE", "LAE-POM"]},
            },
        )

        RatecardConfig.objects.update_or_create(
            ratecard=rc_buy,
            defaults={
                "dim_factor_kg_per_m3": Decimal("167.00"),
                "rate_strategy": "FLAT_PER_KG",
                "created_at": now(),
            },
        )

        stations = {s.iata: s for s in Stations.objects.all()}

        # Ensure all PNG domestic station codes exist with curated names
        needed_iatas = set(DOMESTIC_RATES.keys()) | set(
            i for dests in DOMESTIC_RATES.values() for i in dests.keys()
        )
        created_count = 0
        updated_count = 0
        for code in sorted(needed_iatas):
            city, country = STATION_INFO.get(code, (code, "PG"))
            station, created = Stations.objects.get_or_create(
                iata=code, defaults={"city": city, "country": country}
            )
            if created:
                created_count += 1
            else:
                # Update blank placeholders if present
                should_update = False
                if not station.city or station.city.strip() in ("", code):
                    station.city = city
                    should_update = True
                if not station.country or station.country.strip() == "":
                    station.country = country
                    should_update = True
                if should_update:
                    station.save(update_fields=["city", "country"])
                    updated_count += 1
        if created_count or updated_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Created {created_count}, updated {updated_count} PNG station(s) for domestic rates."
                )
            )
        stations = {s.iata: s for s in Stations.objects.all()}

        self.stdout.write("Updating domestic lanes and rates...")
        for origin_iata, destinations in DOMESTIC_RATES.items():
            for dest_iata, rate_per_kg in destinations.items():
                if origin_iata not in stations or dest_iata not in stations:
                    self.stdout.write(self.style.WARNING(f"Skipping {origin_iata}-{dest_iata}: Station not found in database. Please seed stations first."))
                    continue

                lane, _ = Lanes.objects.update_or_create(
                    ratecard=rc_buy,
                    origin=stations[origin_iata],
                    dest=stations[dest_iata],
                    defaults={"is_direct": True},
                )
                LaneBreaks.objects.update_or_create(
                    lane=lane, break_code="FLAT", defaults={"per_kg": Decimal(rate_per_kg)}
                )
        self.stdout.write(self.style.SUCCESS("Finished updating domestic lanes and rates."))

        # Quick validation summary per origin
        total_expected = 0
        total_lanes = 0
        total_flat_breaks = 0
        for origin_iata, destinations in DOMESTIC_RATES.items():
            origin = stations.get(origin_iata)
            if not origin:
                continue
            # Only count destinations that exist
            existing_dests = [d for d in destinations.keys() if d in stations]
            expected = len(existing_dests)
            lanes_qs = Lanes.objects.filter(ratecard=rc_buy, origin=origin)
            lanes_count = lanes_qs.count()
            flat_breaks_count = LaneBreaks.objects.filter(lane__in=lanes_qs, break_code="FLAT").count()

            # Compute missing pairs (only among known stations)
            missing = []
            if expected:
                have_pairs = set(
                    lanes_qs.values_list("dest__iata", flat=True)
                )
                missing = [d for d in existing_dests if d not in have_pairs]

            total_expected += expected
            total_lanes += lanes_count
            total_flat_breaks += flat_breaks_count

            missing_str = ", ".join(missing) if missing else "none"
            self.stdout.write(
                f"Origin {origin_iata}: lanes {lanes_count}/{expected}, flat breaks {flat_breaks_count}, missing: {missing_str}"
            )

        self.stdout.write(
            self.style.WARNING(
                f"Totals -> lanes {total_lanes}/{total_expected}, flat breaks: {total_flat_breaks}"
            )
        )

        fee_types = {
            "FREIGHT": FeeTypes.objects.get_or_create(
                code="FREIGHT",
                defaults={
                    "description": "Base Freight",
                    "basis": "PER_KG",
                    "default_tax_pct": Decimal("10.00"),
                },
            )[0],
            "DOC": FeeTypes.objects.get_or_create(
                code="DOC",
                defaults={
                    "description": "Documentation Fee",
                    "basis": "PER_SHIPMENT",
                    "default_tax_pct": Decimal("10.00"),
                },
            )[0],
            "TERM": FeeTypes.objects.get_or_create(
                code="TERM",
                defaults={
                    "description": "Terminal Fee",
                    "basis": "PER_SHIPMENT",
                    "default_tax_pct": Decimal("10.00"),
                },
            )[0],
            "SEC": FeeTypes.objects.get_or_create(
                code="SEC",
                defaults={
                    "description": "Security Surcharge",
                    "basis": "PER_KG",
                    "default_tax_pct": Decimal("10.00"),
                },
            )[0],
            "FUEL": FeeTypes.objects.get_or_create(
                code="FUEL",
                defaults={
                    "description": "Fuel Surcharge",
                    "basis": "PER_KG",
                    "default_tax_pct": Decimal("10.00"),
                },
            )[0],
        }

        fees_data = [
            {"code": "DOC", "amount": "35.00"},
            {"code": "TERM", "amount": "35.00"},
            {"code": "SEC", "amount": "0.20", "min_amount": "5.00"},
            {"code": "FUEL", "amount": "0.40"},
        ]
        for fee_data in fees_data:
            RatecardFees.objects.update_or_create(
                ratecard=rc_buy,
                fee_type=fee_types[fee_data["code"]],
                defaults={
                    "amount": Decimal(fee_data["amount"]),
                    "min_amount": Decimal(fee_data.get("min_amount", "0.00")),
                    "currency": "PGK",
                    "applies_if": {},
                    "created_at": now(),
                },
            )

        # =================================================================
        # 2. SETUP SELL-SIDE (PRICING)
        # =================================================================
        rc_sell, _ = Ratecards.objects.update_or_create(
            provider=provider,
            name="PNG Domestic SELL Menu (PGK Local)",
            effective_date=now().date(),
            defaults={
                "role": "SELL",
                "scope": "DOMESTIC",
                "direction": "DOMESTIC",
                "audience": "PGK_LOCAL",
                "currency": "PGK",
                "status": "ACTIVE",
                "source": "SEEDER",
                "created_at": now(),
                "updated_at": now(),
                "meta": {"rounding_rule": "NEAREST_0_05"},
            },
        )

        services = {
            "AIR_FREIGHT": Services.objects.get_or_create(code="AIR_FREIGHT", defaults={"name": "Air Freight", "basis": "PER_KG"})[0],
            "DOC_FEE": Services.objects.get_or_create(code="DOC_FEE", defaults={"name": "Documentation", "basis": "PER_SHIPMENT"})[0],
            "TERMINAL_FEE": Services.objects.get_or_create(code="TERMINAL_FEE", defaults={"name": "Terminal Handling", "basis": "PER_SHIPMENT"})[0],
            "SECURITY_FEE": Services.objects.get_or_create(code="SECURITY_FEE", defaults={"name": "Security Fee", "basis": "PER_KG"})[0],
            "FUEL_SURCHARGE": Services.objects.get_or_create(code="FUEL_SURCHARGE", defaults={"name": "Fuel Surcharge", "basis": "PER_KG"})[0],
            "CARTAGE": Services.objects.get_or_create(code="CARTAGE", defaults={"name": "Pickup/Delivery", "basis": "PER_KG"})[0],
            "CARTAGE_FSC": Services.objects.get_or_create(code="CARTAGE_FSC", defaults={"name": "Cartage Fuel Surcharge", "basis": "PERCENT_OF"})[0],
        }

        sell_items_data = [
            {"service": "AIR_FREIGHT", "tax_pct": "10.0"},
            {"service": "DOC_FEE", "tax_pct": "10.0"},
            {"service": "TERMINAL_FEE", "tax_pct": "10.0"},
            {"service": "SECURITY_FEE", "tax_pct": "10.0"},
            {"service": "FUEL_SURCHARGE", "tax_pct": "10.0"},
            {"service": "CARTAGE", "amount": "0.80", "min_amount": "80.00", "tax_pct": "10.0"},
            {"service": "CARTAGE_FSC", "amount": "0.10", "percent_of_service_code": "CARTAGE", "tax_pct": "10.0"}, # 10% of CARTAGE
        ]

        sell_items = {}
        for item_data in sell_items_data:
            svc = services[item_data["service"]]
            item, _ = ServiceItems.objects.update_or_create(
                ratecard=rc_sell,
                service=svc,
                defaults={
                    "amount": Decimal(item_data.get("amount", "0.00")),
                    "min_amount": Decimal(item_data.get("min_amount", "0.00")),
                    "percent_of_service_code": item_data.get("percent_of_service_code"),
                    "tax_pct": Decimal(item_data["tax_pct"]),
                    "currency": "PGK",
                    "conditions_json": {},
                },
            )
            sell_items[svc.code] = item

        # 3. LINK BUY COSTS TO SELL ITEMS
        links_data = [
            {"sell_code": "AIR_FREIGHT", "buy_code": "FREIGHT", "type": "COST_PLUS_PCT", "value": "0.18"},
            {"sell_code": "DOC_FEE", "buy_code": "DOC", "type": "PASS_THROUGH"},
            {"sell_code": "TERMINAL_FEE", "buy_code": "TERM", "type": "PASS_THROUGH"},
            {"sell_code": "SECURITY_FEE", "buy_code": "SEC", "type": "PASS_THROUGH"},
            {"sell_code": "FUEL_SURCHARGE", "buy_code": "FUEL", "type": "PASS_THROUGH"},
        ]
        for link_data in links_data:
            SellCostLinksSimple.objects.update_or_create(
                sell_item=sell_items[link_data["sell_code"]],
                buy_fee_code=fee_types[link_data["buy_code"]],
                defaults={
                    "mapping_type": link_data["type"],
                    "mapping_value": Decimal(link_data.get("value", "0.00")),
                },
            )

        self.stdout.write(self.style.SUCCESS("Domestic BUY/SELL seeding complete with actual rates."))
