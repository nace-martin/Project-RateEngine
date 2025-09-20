# backend/pricing/management/commands/seed_all_data.py

import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from accounts.models import CustomUser
from core.models import CurrencyRates, FeeTypes, Providers, Services, Stations
from organizations.models import Organizations
from pricing.models import (
    Audience,
    LaneBreaks,
    Lanes,
    PricingPolicy,
    RatecardConfig,
    RatecardFees,
    Ratecards,
    Routes,
    RouteLegs,
    SellCostLinksSimple,
    ServiceItems,
)


# region -------- Helper Functions --------
# CORRECTED: Removed max_service_level from initial creation
def upsert_station(iata, city, country):
    station, _ = Stations.objects.update_or_create(
        iata=iata,
        defaults={
            "city": city,
            "country": country,
        },
    )
    return station


def upsert_provider(name, ptype):
    provider, _ = Providers.objects.get_or_create(
        name=name, defaults={"provider_type": ptype}
    )
    return provider


def ensure_fee_type(code, description, basis, default_tax_pct=Decimal("10.00")):
    ft, _ = FeeTypes.objects.get_or_create(
        code=code,
        defaults={
            "description": description,
            "basis": basis,
            "default_tax_pct": default_tax_pct,
        },
    )
    return ft


def ensure_service(code, name, basis):
    svc, _ = Services.objects.get_or_create(
        code=code, defaults={"name": name, "basis": basis}
    )
    return svc


def ensure_ratecard(
    provider,
    name,
    role,
    scope,
    direction,
    currency,
    audience=None,
    source="CATALOG",
    status="PUBLISHED",
    rate_strategy="IATA_BREAKS",
):
    audience_code = audience or "OVERSEAS_AGENT_PREPAID"
    audience_obj = Audience.get_or_create_from_code(audience_code)
    rc, _ = Ratecards.objects.update_or_create(
        name=name,
        provider=provider,
        role=role,
        scope=scope,
        direction=direction,
        defaults=dict(
            audience=audience_obj,
            currency=currency,
            source=source,
            status=status,
            effective_date=now().date(),
            meta={},
            created_at=now(),
            updated_at=now(),
        ),
    )
    RatecardConfig.objects.get_or_create(
        ratecard=rc,
        defaults={
            "dim_factor_kg_per_m3": Decimal("167.00"),
            "rate_strategy": rate_strategy,
            "created_at": now(),
        },
    )
    return rc


def ensure_lane_with_breaks(rc, origin, dest, airline, is_direct, breaks, via=None):
    lane, _ = Lanes.objects.update_or_create(
        ratecard=rc,
        origin=origin,
        dest=dest,
        defaults={"airline": airline, "is_direct": is_direct, "via": via},
    )
    LaneBreaks.objects.filter(lane=lane).delete()
    for b in breaks:
        if b["code"] == "MIN":
            LaneBreaks.objects.create(
                lane=lane, break_code="MIN", min_charge=b["min"]
            )
        else:
            LaneBreaks.objects.create(lane=lane, break_code=b["code"], per_kg=b["kg"])
    return lane


def add_fee(
    rc,
    fee_type_code,
    currency,
    amount,
    *,
    min_amount=None,
    max_amount=None,
    applies_if=None,
    percent_of_code=None,
    per_kg_threshold=None,
):
    ft = FeeTypes.objects.get(code=fee_type_code)
    RatecardFees.objects.update_or_create(
        ratecard=rc,
        fee_type=ft,
        defaults={
            "currency": currency,
            "amount": amount,
            "applies_if": applies_if if applies_if is not None else {},
            "created_at": now(),
            "min_amount": min_amount,
            "max_amount": max_amount,
            "percent_of_code": percent_of_code,
            "per_kg_threshold": per_kg_threshold,
        },
    )


def add_service_item(
    rc,
    service_code,
    currency,
    amount,
    *,
    min_amount=None,
    max_amount=None,
    tax_pct=0,
    percent_of_service_code=None,
    item_code=None,
):
    svc = Services.objects.get(code=service_code)
    item, _ = ServiceItems.objects.update_or_create(
        ratecard=rc,
        service=svc,
        defaults={
            "currency": currency,
            "amount": amount,
            "tax_pct": tax_pct,
            "conditions_json": {},
            "min_amount": min_amount,
            "max_amount": max_amount,
            "percent_of_service_code": percent_of_service_code,
            "item_code": item_code,
        },
    )
    return item


def add_sell_cost_link(sell_item, buy_fee_code, mapping_type, mapping_value=None):
    ft = FeeTypes.objects.get(code=buy_fee_code)
    SellCostLinksSimple.objects.update_or_create(
        sell_item=sell_item,
        buy_fee=ft,  # FK field name
        defaults={"mapping_type": mapping_type, "mapping_value": Decimal(str(mapping_value)) if mapping_value is not None else None},
    )


def ensure_fx(base, quote, rate, source="manual"):
    CurrencyRates.objects.update_or_create(
        base_ccy=base,
        quote_ccy=quote,
        defaults={"rate": Decimal(str(rate)), "as_of_ts": now(), "source": source},
    )


def ensure_policy(audience_code, *, caf_buy_pct=0.05, caf_sell_pct=0.10, gst_applies=True, gst_pct=10):
    audience = Audience.get_or_create_from_code(audience_code)
    PricingPolicy.objects.update_or_create(
        audience=audience,  # FK not .code
        defaults={
            "caf_buy_pct": Decimal(str(caf_buy_pct)),
            "caf_sell_pct": Decimal(str(caf_sell_pct)),
            "gst_applies": gst_applies,
            "gst_pct": Decimal(str(gst_pct)),
        },
    )


# endregion

# region -------- Seeding Logic --------
@transaction.atomic
def seed_core_data():
    """Seeds foundational data like airports, providers, fees, and services."""
    upsert_station("POM", "Port Moresby", "PG")
    upsert_station("LAE", "Lae", "PG")
    upsert_station("BNE", "Brisbane", "AU")
    upsert_station("SYD", "Sydney", "AU")
    upsert_station("SIN", "Singapore", "SG")
    upsert_station("HKG", "Hong Kong", "HK")
    upsert_station("RAB", "Rabaul", "PG")
    upsert_station("MAG", "Madang", "PG")
    upsert_station("GUR", "Gurney", "PG")
    upsert_station("BUA", "Buka", "PG")
    upsert_station("DAU", "Daru", "PG")
    upsert_station("GKA", "Goroka", "PG")
    upsert_station("HKN", "Hoskins", "PG")
    upsert_station("KVG", "Kavieng", "PG")
    upsert_station("KIE", "Kieta", "PG")
    upsert_station("WWK", "Wewak", "PG")

    upsert_provider("Air Niugini", "CARRIER")
    upsert_provider("Qantas Freight", "CARRIER")
    upsert_provider("Maersk Air Freight", "AGENT")
    upsert_provider("Express Freight Management", "AGENT")
    upsert_provider("PNG Domestic Carrier", "CARRIER")

    ensure_fee_type("X_RAY", "Mandatory X-Ray Screening", "PER_KG")
    ensure_fee_type("CTO", "Cargo Terminal Operator (Terminal Fee)", "PER_KG")
    ensure_fee_type("FUEL", "Fuel Surcharge", "PER_KG")
    ensure_fee_type("SECURITY", "Security Surcharge", "PER_KG")
    ensure_fee_type("FREIGHT", "Base Air Freight", "PER_KG")
    ensure_fee_type("PICKUP", "Pickup Linehaul", "PER_KG")
    ensure_fee_type("PICKUP_FUEL", "Pickup Fuel Surcharge", "PERCENT_OF")
    ensure_fee_type("DOC_FEE", "Export Document Fee", "PER_SHIPMENT")
    ensure_fee_type("AGENCY_FEE", "Export Agency Fee", "PER_SHIPMENT")
    ensure_fee_type("AWB_FEE", "Origin AWB Fee", "PER_SHIPMENT")
    ensure_fee_type("DOC", "Documentation Fee", "PER_SHIPMENT")
    ensure_fee_type("TERM", "Terminal Fee", "PER_SHIPMENT")
    ensure_fee_type("SEC", "Security Surcharge", "PER_KG")

    ensure_service("CLEARANCE_EXP", "Export Customs Clearance", "PER_SHIPMENT")
    ensure_service("CLEARANCE_IMP", "Import Customs Clearance", "PER_SHIPMENT")
    ensure_service("CARTAGE_POM", "Cartage - POM Metro", "PER_KG")
    ensure_service("FUEL_LEVY", "Fuel Levy", "PERCENT_OF")
    ensure_service("AIR_FREIGHT", "Air Freight Charge", "PER_KG")
    ensure_service("CUSTOMS_CLEARANCE", "Customs Clearance", "PER_SHIPMENT")
    ensure_service("AGENCY_FEE", "Agency Fee", "PER_SHIPMENT")
    ensure_service("CUSTOMS_ENTRY_PAGE", "Customs Entry (per page)", "PER_PAGE")
    ensure_service("DOCUMENTATION_FEE", "Documentation Fee", "PER_SHIPMENT")
    ensure_service("HANDLING_GENERAL", "Handling Fee - General Cargo", "PER_SHIPMENT")
    ensure_service("TERMINAL_FEE_INT", "International Terminal Fee", "PER_SHIPMENT")
    ensure_service("CARTAGE_DELIVERY", "Cartage & Delivery", "PER_KG")
    ensure_service("FUEL_SURCHARGE_CARTAGE", "Fuel Surcharge on Cartage", "PERCENT_OF")
    ensure_service("DISBURSEMENT_FEE", "Disbursement Fee", "PERCENT_OF")


@transaction.atomic
def seed_all_rates():
    provider = Providers.objects.get(name="PNG Domestic Carrier")

    rc_buy_dom = ensure_ratecard(
        provider=provider,
        name="PNG Domestic BUY Rates (Flat per KG)",
        role="BUY",
        scope="DOMESTIC",
        direction="DOMESTIC",
        currency="PGK",
        audience="PNG_CUSTOMER_PREPAID",
        rate_strategy="FLAT_PER_KG",
    )
    rc_buy_dom.meta = {"d2d_available_between": ["POM-LAE", "LAE-POM"]}
    rc_buy_dom.save(update_fields=["meta"])

    stations = {s.iata: s for s in Stations.objects.all()}

    DOMESTIC_RATES = {
        "POM": {"GUR": "7.85","BUA": "19.35","DAU": "11.05","GKA": "8.30","HKN": "11.55","KVG": "17.65","KIE": "20.45","LAE": "6.10","MAG": "8.75","RAB": "15.45","WWK": "13.75"},
        "LAE": {"GKA": "9.95","HKN": "11.05","KVG": "12.75","POM": "6.10","RAB": "11.60","WWK": "12.10"},
    }

    for origin_iata, destinations in DOMESTIC_RATES.items():
        for dest_iata, rate_per_kg in destinations.items():
            if origin_iata in stations and dest_iata in stations:
                lane, _ = Lanes.objects.update_or_create(
                    ratecard=rc_buy_dom,
                    origin=stations[origin_iata],
                    dest=stations[dest_iata],
                    defaults={"is_direct": True},
                )
                LaneBreaks.objects.update_or_create(
                    lane=lane, break_code="FLAT", defaults={"per_kg": Decimal(rate_per_kg)}
                )

    # International BUY
    provider = upsert_provider("Maersk Air Freight", "AGENT")
    bne = upsert_station("BNE", "Brisbane", "AU")
    syd = upsert_station("SYD", "Sydney", "AU")
    pom = upsert_station("POM", "Port Moresby", "PG")

    bne_rc = ensure_ratecard(provider, "EFM BNE->POM BUY (AUD)", "BUY", "INTERNATIONAL", "EXPORT", "AUD", audience="AU_AGENT_PREPAID")
    ensure_lane_with_breaks(bne_rc, bne, pom, airline="PX", is_direct=True, breaks=[
        {"code": "MIN", "min": Decimal("330.00")},
        {"code": "45", "kg": Decimal("7.05")},
        {"code": "100", "kg": Decimal("6.75")},
    ])
    add_fee(bne_rc, "X_RAY", "AUD", "0.36", min_amount="70.00")
    add_fee(bne_rc, "CTO", "AUD", "0.30", min_amount="30.00")
    add_fee(bne_rc, "FUEL", "AUD", "0.80")
    add_fee(bne_rc, "SECURITY", "AUD", "0.20")

    syd_rc = ensure_ratecard(provider, "EFM SYD->POM BUY (AUD)", "BUY", "INTERNATIONAL", "EXPORT", "AUD", audience="AU_AGENT_PREPAID")
    ensure_lane_with_breaks(syd_rc, syd, pom, airline="PX", is_direct=True, breaks=[
        {"code": "MIN", "min": Decimal("330.00")},
        {"code": "45", "kg": Decimal("7.05")},
        {"code": "100", "kg": Decimal("6.75")},
    ])
    add_fee(syd_rc, "X_RAY", "AUD", "0.36", min_amount="70.00")
    add_fee(syd_rc, "CTO", "AUD", "0.30", min_amount="30.00")
    add_fee(syd_rc, "FUEL", "AUD", "0.80")
    add_fee(syd_rc, "SECURITY", "AUD", "0.20")

    efm_provider = upsert_provider("Express Freight Management", "AGENT")
    efm_rc = ensure_ratecard(
        efm_provider,
        "EFM PGK Import SELL Menu 2025 (Prepaid)",
        "SELL","INTERNATIONAL","IMPORT","PGK",
        audience="PNG_CUSTOMER_PREPAID"
    )
    from datetime import date
    efm_rc.effective_date = date(2025, 1, 1)
    efm_rc.save(update_fields=["effective_date"])

    add_service_item(efm_rc, "CUSTOMS_CLEARANCE", "PGK", Decimal("300.00"))
    add_service_item(efm_rc, "AGENCY_FEE", "PGK", Decimal("250.00"))

    efm_collect_rc = ensure_ratecard(
        efm_provider,
        "EFM PGK Import SELL Menu 2025 (Collect)",
        "SELL","INTERNATIONAL","IMPORT","PGK",
        audience="OVERSEAS_AGENT_COLLECT"
    )
    efm_collect_rc.effective_date = date(2025, 1, 1)
    efm_collect_rc.save(update_fields=["effective_date"])
    add_service_item(efm_collect_rc, "CUSTOMS_CLEARANCE", "PGK", Decimal("300.00"))
    add_service_item(efm_collect_rc, "AGENCY_FEE", "PGK", Decimal("250.00"))


@transaction.atomic
def seed_financials_and_routes():
    """Seeds FX, policies, and routes."""
    ensure_fx("AUD", "PGK", "2.65")
    ensure_fx("USD", "PGK", "3.75")
    ensure_fx("PGK", "AUD", "0.38")
    ensure_fx("PGK", "USD", "0.27")

    ensure_policy("PNG_CUSTOMER_PREPAID", gst_applies=True, gst_pct=10)
    ensure_policy("AU_AGENT_PREPAID", gst_applies=False, gst_pct=0)
    ensure_policy("OVERSEAS_AGENT_COLLECT", gst_applies=False, gst_pct=0)
    
    route, _ = Routes.objects.get_or_create(
        origin_country="AU", dest_country="PG", shipment_type="IMPORT",
        defaults={"name": "AU->PG", "requires_manual_rate": False}
    )
    bne = Stations.objects.get(iata="BNE")
    pom = Stations.objects.get(iata="POM")
    RouteLegs.objects.update_or_create(
        route=route, sequence=1, defaults={"origin": bne, "dest": pom}
    )


@transaction.atomic
def seed_organizations_and_users():
    """Seeds sample organizations and test users."""
    png_aud = Audience.get_or_create_from_code("PNG_CUSTOMER_PREPAID")
    au_aud  = Audience.get_or_create_from_code("AU_AGENT_PREPAID")

    # Use FK field 'audience' instead of non-existent 'audience_code'
    Organizations.objects.update_or_create(
        name="PNG Exporter Ltd",
        defaults={
            "audience": png_aud.code,
            "default_sell_currency": "PGK",
            "gst_pct": Decimal("10.00"),
        },
    )
    Organizations.objects.update_or_create(
        name="AU Importer Pty Ltd",
        defaults={
            "audience": au_aud.code,
            "default_sell_currency": "AUD",
            "gst_pct": Decimal("0.00"),
        },
    )

    if not CustomUser.objects.filter(username="testadmin").exists():
        CustomUser.objects.create_superuser("testadmin", "admin@example.com", "testpassword")
    if not CustomUser.objects.filter(username="testuser").exists():
        CustomUser.objects.create_user("testuser", "user@example.com", "testpassword")

# endregion


class Command(BaseCommand):
    help = "Seeds the database with a complete and realistic sandbox dataset from all sources."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("--- Starting Comprehensive Seeding ---"))

        self.stdout.write("Step 1: Seeding core data (airports, providers, fees)...")
        seed_core_data()

        self.stdout.write("Step 2: Seeding all BUY and SELL rates...")
        seed_all_rates()

        self.stdout.write("Step 3: Seeding financial data (FX, policies) and routes...")
        seed_financials_and_routes()
        
        self.stdout.write("Step 4: Seeding sample organizations and users...")
        seed_organizations_and_users()

        self.stdout.write(self.style.SUCCESS("--- Comprehensive Seeding Completed Successfully ---"))