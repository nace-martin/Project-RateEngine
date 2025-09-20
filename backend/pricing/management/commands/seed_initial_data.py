# backend/pricing/management/commands/seed_initial_data.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from decimal import Decimal

# Ensure this import path matches your project structure
from core.models import (
    Providers,
    Stations,
    FeeTypes,
    Services,
    CurrencyRates,
)
from pricing.models import (
    Audience,
    Ratecards,
    RatecardConfig,
    Lanes,
    LaneBreaks,
    RatecardFees,
    ServiceItems,
    SellCostLinksSimple,
    PricingPolicy,
)

#region -------- Helper Functions --------
# CORRECTED FUNCTION
def upsert_station(iata, city, country):
    station, _ = Stations.objects.get_or_create(
        iata=iata,
        defaults={"city": city, "country": country}
    )
    return station

def upsert_provider(name, ptype):
    return Providers.objects.get_or_create(name=name, defaults={"provider_type": ptype})[0]

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
    svc, _ = Services.objects.get_or_create(code=code, defaults={"name": name, "basis": basis})
    return svc


def ensure_ratecard(provider, name, role, scope, direction, currency, audience=None, source="CATALOG", status="PUBLISHED"):
    audience_code = audience or "OVERSEAS_AGENT_PREPAID"
    audience_obj = Audience.get_or_create_from_code(audience_code)
    defaults = dict(
        provider=provider,
        role=role,
        scope=scope,
        direction=direction,
        audience=audience_obj,
        currency=currency,
        source=source,
        status=status,
        effective_date=now().date(),
        meta={},
        created_at=now(),
        updated_at=now(),
    )
    rc, created = Ratecards.objects.get_or_create(name=name, defaults=defaults)

    if not created:
        rc.audience = audience_obj
        rc.updated_at = now()
        rc.save(update_fields=["audience", "updated_at"])

    RatecardConfig.objects.get_or_create(
        ratecard_id=rc.id,
        defaults={
            "dim_factor_kg_per_m3": Decimal("167.00"),
            "rate_strategy": "IATA_BREAKS",
            "created_at": now(),
        },
    )
    return rc

def ensure_lane_with_breaks(rc, origin, dest, airline, is_direct, breaks, via=None):
    lane, _ = Lanes.objects.get_or_create(
        ratecard=rc, origin=origin, dest=dest,
        defaults={"airline": airline, "is_direct": is_direct, "via": via},
    )
    # Clear existing breaks to ensure a clean slate
    LaneBreaks.objects.filter(lane=lane).delete()
    for b in breaks:
        if b["code"] == "MIN":
            LaneBreaks.objects.create(lane=lane, break_code="MIN", min_charge=b["min"])
        else:
            LaneBreaks.objects.create(lane=lane, break_code=b["code"], per_kg=b["kg"])
    return lane

def add_fee(rc, fee_type_code, currency, amount, *, min_amount=None, max_amount=None, applies_if=None, percent_of_code=None, per_kg_threshold=None):
    ft = FeeTypes.objects.get(code=fee_type_code)
    defaults = {
        "currency": currency,
        "amount": amount,
        "applies_if": applies_if if applies_if is not None else {},
        "created_at": now(),
        "min_amount": min_amount,
        "max_amount": max_amount,
        "percent_of_code": percent_of_code,
        "per_kg_threshold": per_kg_threshold
    }
    RatecardFees.objects.update_or_create(ratecard_id=rc.id, fee_type_id=ft.id, defaults=defaults)

def add_service_item(rc, service_code, currency, amount, *, min_amount=None, max_amount=None, tax_pct=0, percent_of_service_code=None):
    svc = Services.objects.get(code=service_code)
    defaults = {
        "currency": currency,
        "amount": amount,
        "tax_pct": tax_pct,
        "conditions_json": {},
        "min_amount": min_amount,
        "max_amount": max_amount,
        "percent_of_service_code": percent_of_service_code
    }
    return ServiceItems.objects.update_or_create(ratecard_id=rc.id, service_id=svc.id, defaults=defaults)[0]

def add_sell_cost_link(sell_item, buy_fee_code, mapping_type, mapping_value=None):
    ft = FeeTypes.objects.get(code=buy_fee_code)
    SellCostLinksSimple.objects.update_or_create(
        sell_item=sell_item, buy_fee_code=ft,
        defaults={"mapping_type": mapping_type, "mapping_value": mapping_value}
    )

def ensure_fx(base, quote, rate, source="manual", rate_type="BUY"):
    CurrencyRates.objects.update_or_create(
        base_ccy=base, quote_ccy=quote,
        defaults={"rate": rate, "as_of_ts": now(), "source": source, "rate_type": rate_type}
    )

def ensure_policy(audience_code, *, caf_buy_pct=0.05, caf_sell_pct=0.10, gst_applies=True, gst_pct=10):
    audience = Audience.get_or_create_from_code(audience_code)
    PricingPolicy.objects.update_or_create(
        audience=audience.code,
        defaults={"caf_buy_pct": caf_buy_pct, "caf_sell_pct": caf_sell_pct, "gst_applies": gst_applies, "gst_pct": gst_pct}
    )
#endregion

#region -------- Seeding Functions --------
@transaction.atomic
def seed_core_data():
    """Seeds core airports, providers, fees, and services."""
    upsert_station("POM", "Port Moresby", "PG")
    upsert_station("LAE", "Lae", "PG")
    upsert_station("BNE", "Brisbane", "AU")
    upsert_station("SYD", "Sydney", "AU")
    upsert_station("SIN", "Singapore", "SG")
    upsert_station("HKG", "Hong Kong", "HK")
    upsert_station("RAB", "Rabaul", "PG")
    upsert_station("MAG", "Madang", "PG")

    upsert_provider("Air Niugini", "CARRIER")
    upsert_provider("Qantas Freight", "CARRIER")
    upsert_provider("Maersk Air Freight", "AGENT")

    ensure_fee_type("X_RAY", "Mandatory X-Ray Screening", "PER_KG")
    ensure_fee_type("CTO", "Cargo Terminal Operator (Terminal Fee)", "PER_KG")
    ensure_fee_type("FUEL", "Fuel Surcharge", "PER_KG")
    ensure_fee_type("SECURITY", "Security Surcharge", "PER_KG")
    ensure_fee_type("FREIGHT", "Base Air Freight", "PER_KG")

    ensure_service("CLEARANCE_EXP", "Export Customs Clearance", "PER_SHIPMENT")
    ensure_service("CLEARANCE_IMP", "Import Customs Clearance", "PER_SHIPMENT")
    ensure_service("CARTAGE_POM", "Cartage - POM Metro", "PER_KG")
    ensure_service("FUEL_LEVY", "Fuel Levy", "PERCENT_OF")
    ensure_service("AIR_FREIGHT", "Air Freight Charge", "PER_KG")

@transaction.atomic
def seed_all_buy_rates():
    """Seeds a comprehensive set of BUY rate cards."""
    pom = Stations.objects.get(iata="POM")
    lae = Stations.objects.get(iata="LAE")
    bne = Stations.objects.get(iata="BNE")
    sin = Stations.objects.get(iata="SIN")
    px = Providers.objects.get(name="Air Niugini")
    maersk = Providers.objects.get(name="Maersk Air Freight")

    rc_dom = ensure_ratecard(px, "Air Niugini Domestic BUY (PGK)", "BUY", "DOMESTIC", "EXPORT", "PGK")
    ensure_lane_with_breaks(
        rc_dom, pom, lae, "PX", True,
        [{"code": "MIN", "min": 150.00}, {"code": "100", "kg": 2.50}, {"code": "500", "kg": 2.20}]
    )
    add_fee(rc_dom, "SECURITY", "PGK", "0.20", min_amount="25.00")

    rc_bne = ensure_ratecard(maersk, "EFM AU->POM BUY (AUD)", "BUY", "INTERNATIONAL", "EXPORT", "AUD")
    ensure_lane_with_breaks(
        rc_bne, bne, pom, "NU", True,
        [{"code": "MIN", "min": 330.00}, {"code": "45", "kg": 7.05}, {"code": "100", "kg": 6.75}, {"code": "250", "kg": 6.55}, {"code": "500", "kg": 6.25}, {"code": "1000", "kg": 5.95}]
    )
    add_fee(rc_bne, "X_RAY", "AUD", "0.36", min_amount="70.00")
    add_fee(rc_bne, "CTO", "AUD", "0.30", min_amount="30.00")

    rc_sin = ensure_ratecard(maersk, "Agent POM->SIN BUY (USD)", "BUY", "INTERNATIONAL", "EXPORT", "USD")
    ensure_lane_with_breaks(
        rc_sin, pom, sin, "NU", False,
        [{"code": "MIN", "min": 190.00}, {"code": "45", "kg": 7.19}, {"code": "100", "kg": 6.90}, {"code": "250", "kg": 6.60}, {"code": "500", "kg": 6.40}, {"code": "1000", "kg": 6.20}]
    )
    add_fee(rc_sin, "FUEL", "USD", "0.56")
    add_fee(rc_sin, "SECURITY", "USD", "0.143")

@transaction.atomic
def seed_all_sell_menus_and_links():
    """Seeds all SELL menus and links them to BUY costs."""
    our_company = Providers.objects.get(name="Maersk Air Freight")

    rc_exp = ensure_ratecard(our_company, "PGK Export SELL Menu", "SELL", "INTERNATIONAL", "EXPORT", "PGK", "PNG_CUSTOMER_PREPAID")
    add_service_item(rc_exp, "CLEARANCE_EXP", "PGK", "350.00")
    add_service_item(rc_exp, "CARTAGE_POM", "PGK", "0.80", min_amount="120.00", tax_pct="10.0")
    add_service_item(rc_exp, "FUEL_LEVY", "PGK", "0.15", percent_of_service_code="CARTAGE_POM", tax_pct="10.0")
    exp_freight = add_service_item(rc_exp, "AIR_FREIGHT", "PGK", "0.0")

    rc_imp = ensure_ratecard(our_company, "PGK Import SELL Menu", "SELL", "INTERNATIONAL", "IMPORT", "PGK", "PNG_CUSTOMER_PREPAID")
    add_service_item(rc_imp, "CLEARANCE_IMP", "PGK", "450.00", min_amount="450.00")
    add_service_item(rc_imp, "CARTAGE_POM", "PGK", "0.85", min_amount="150.00", tax_pct="10.0")
    add_service_item(rc_imp, "FUEL_LEVY", "PGK", "0.15", percent_of_service_code="CARTAGE_POM", tax_pct="10.0")
    imp_freight = add_service_item(rc_imp, "AIR_FREIGHT", "PGK", "0.0")

    rc_collect = ensure_ratecard(our_company, "AUD Collect SELL Menu", "SELL", "INTERNATIONAL", "IMPORT", "AUD", "OVERSEAS_AGENT_COLLECT")
    add_service_item(rc_collect, "CLEARANCE_IMP", "AUD", "200.00")
    collect_freight = add_service_item(rc_collect, "AIR_FREIGHT", "AUD", "0.0")

    for item in [exp_freight, imp_freight, collect_freight]:
        add_sell_cost_link(item, "FREIGHT", "PASS_THROUGH")
        add_sell_cost_link(item, "FUEL", "COST_PLUS_PCT", mapping_value="0.10")
        add_sell_cost_link(item, "SECURITY", "PASS_THROUGH")
        add_sell_cost_link(item, "X_RAY", "PASS_THROUGH")
        add_sell_cost_link(item, "CTO", "PASS_THROUGH")

@transaction.atomic
def seed_financials():
    """Seeds exchange rates and pricing policies."""
    ensure_fx("AUD", "PGK", "2.65")
    ensure_fx("USD", "PGK", "3.75")
    ensure_fx("PGK", "AUD", "0.38")
    ensure_fx("PGK", "USD", "0.27")

    # Add SELL rates
    ensure_fx("PGK", "AUD", "0.38", rate_type="SELL")
    ensure_fx("PGK", "USD", "0.27", rate_type="SELL")

    ensure_policy("PNG_CUSTOMER_PREPAID", gst_applies=True, gst_pct=10)
    ensure_policy("AU_AGENT_PREPAID", gst_applies=False, gst_pct=0)
    ensure_policy("OVERSEAS_AGENT_COLLECT", gst_applies=False, gst_pct=0, caf_buy_pct=0.03, caf_sell_pct=0.05)
#endregion

class Command(BaseCommand):
    help = "Seeds the database with a complete and realistic sandbox dataset."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Seeding comprehensive sandbox data..."))
        
        self.stdout.write("Seeding core data (airports, providers, fees)...")
        seed_core_data()
        
        self.stdout.write("Seeding all BUY rate cards...")
        seed_all_buy_rates()
        
        self.stdout.write("Seeding all SELL menus and linking to costs...")
        seed_all_sell_menus_and_links()

        self.stdout.write("Seeding financial data (FX rates and policies)...")
        seed_financials()

        self.stdout.write(self.style.SUCCESS("Comprehensive sandbox data has been seeded successfully."))