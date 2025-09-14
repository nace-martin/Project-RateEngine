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
}

class Command(BaseCommand):
    help = "Seeds the database with initial domestic BUY and SELL rate data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding domestic BUY and SELL rate data with actuals...")

        # =================================================================
        # 1. SETUP BUY-SIDE (COSTS)
        # =================================================================
        provider, _ = Providers.objects.get_or_create(name="PNG Domestic Carrier")

        rc_buy, _ = Ratecards.objects.update_or_create(
            name="PNG Domestic BUY Rates (Flat per KG)",
            defaults={
                "provider": provider, "role": "BUY", "scope": "DOMESTIC",
                "direction": "DOMESTIC", "rate_strategy": "FLAT_PER_KG",
                "currency": "PGK", "status": "ACTIVE", "source": "SEEDER",
                "effective_date": now().date(), "created_at": now(), "updated_at": now(),
                 "meta": json.dumps({"d2d_available_between": ["POM-LAE", "LAE-POM"]}),
            }
        )

        RatecardConfig.objects.update_or_create(
            ratecard=rc_buy, defaults={"dim_factor_kg_per_m3": Decimal("167.00")}
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
                    origin=stations[origin_iata], dest=stations[dest_iata],
                    defaults={"is_direct": True}
                )
                LaneBreaks.objects.update_or_create(
                    lane=lane, break_code="FLAT", defaults={"per_kg": Decimal(rate_per_kg)}
                )
        self.stdout.write(self.style.SUCCESS("Finished updating domestic lanes and rates."))

        fee_types = {
            "FREIGHT": FeeTypes.objects.get_or_create(code="FREIGHT", defaults={"name": "Base Freight", "basis": "PER_KG"})[0],
            "DOC": FeeTypes.objects.get_or_create(code="DOC", defaults={"name": "Documentation Fee", "basis": "PER_SHIPMENT"})[0],
            "TERM": FeeTypes.objects.get_or_create(code="TERM", defaults={"name": "Terminal Fee", "basis": "PER_SHIPMENT"})[0],
            "SEC": FeeTypes.objects.get_or_create(code="SEC", defaults={"name": "Security Surcharge", "basis": "PER_KG"})[0],
            "FUEL": FeeTypes.objects.get_or_create(code="FUEL", defaults={"name": "Fuel Surcharge", "basis": "PER_KG"})[0],
        }

        fees_data = [
            {"code": "DOC", "amount": "35.00"},
            {"code": "TERM", "amount": "35.00"},
            {"code": "SEC", "amount": "0.20", "min_amount": "5.00"},
            {"code": "FUEL", "amount": "0.35"},
        ]
        for fee_data in fees_data:
            RatecardFees.objects.update_or_create(
                ratecard=rc_buy, fee_type=fee_types[fee_data["code"]],
                defaults={
                    "amount": Decimal(fee_data["amount"]),
                    "min_amount": Decimal(fee_data.get("min_amount", "0.00")),
                    "currency": "PGK", "created_at": now()
                }
            )

        # =================================================================
        # 2. SETUP SELL-SIDE (PRICING)
        # =================================================================
        rc_sell, _ = Ratecards.objects.update_or_create(
            name="PNG Domestic SELL Menu (PGK Local)",
            defaults={
                "role": "SELL", "scope": "DOMESTIC", "direction": "DOMESTIC",
                "audience": "PGK_LOCAL", "currency": "PGK", "status": "ACTIVE",
                "source": "SEEDER", "effective_date": now().date(), "created_at": now(),
                "updated_at": now(), "meta": json.dumps({"rounding_rule": "NEAREST_0_05"})
            }
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
                ratecard=rc_sell, service=svc,
                defaults={
                    "amount": Decimal(item_data.get("amount", "0.00")),
                    "min_amount": Decimal(item_data.get("min_amount", "0.00")),
                    "percent_of_service_code": item_data.get("percent_of_service_code"),
                    "tax_pct": Decimal(item_data["tax_pct"]), "currency": "PGK"
                }
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
                defaults={
                    "buy_fee_code": fee_types[link_data["buy_code"]],
                    "mapping_type": link_data["type"],
                    "mapping_value": Decimal(link_data.get("value", "0.00"))
                }
            )

        self.stdout.write(self.style.SUCCESS("Domestic BUY/SELL seeding complete with actual rates."))
