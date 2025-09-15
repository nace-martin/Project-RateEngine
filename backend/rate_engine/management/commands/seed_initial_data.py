# backend/rate_engine/management/commands/seed_initial_data.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from decimal import Decimal

# Ensure this import path matches your project structure
from rate_engine.models import (
    Providers, Stations,
    Ratecards, RatecardConfig, Lanes, LaneBreaks,
    FeeTypes, RatecardFees, ServiceItems, SellCostLinksSimple, Services,
    CurrencyRates, PricingPolicy,
)

#region -------- Helper Functions --------
def upsert_station(iata, city, country):
    return Stations.objects.get_or_create(iata=iata, defaults={"city": city, "country": country})[0]

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
    rc, _ = Ratecards.objects.get_or_create(
        name=name,
        defaults=dict(
            provider=provider, role=role, scope=scope, direction=direction,
            audience=audience, currency=currency, source=source,
            status=status, effective_date=now().date(), meta={},
        ),
    )
    RatecardConfig.objects.get_or_create(
        ratecard_id=rc.id,
        defaults={
            "dim_factor_kg_per_m3": Decimal("167.00"),
            "rate_strategy": "IATA_BREAKS",
        },
    )
    return rc

def ensure_lane_with_breaks(rc, origin, dest, airline, is_direct, breaks, via=None):
    lane, _ = Lanes.objects.get_or_create(
        ratecard=rc, origin=origin, dest=dest,
        defaults={"airline": airline, "is_direct": is_direct, "via": via},
    )
    if lane.airline != airline or lane.is_direct != is_direct:
        lane.airline = airline
        lane.is_direct = is_direct
        if via: lane.via = via
        lane.save()

    for b in breaks:
        if b["code"] == "MIN":
            LaneBreaks.objects.update_or_create(
                lane=lane, break_code="MIN",
                defaults={"min_charge": b["min"], "per_kg": None},
            )
        else:
            LaneBreaks.objects.update_or_create(
                lane=lane, break_code=b["code"],
                defaults={"min_charge": None, "per_kg": b["kg"]},
            )
    return lane

def add_fee(rc, fee_type_code, currency, amount, *, min_amount=None, max_amount=None, applies_if=None, percent_of_code=None, per_kg_threshold=None):
    ft = FeeTypes.objects.get(code=fee_type_code)
    defaults = {
        "currency": currency,
        "amount": amount,
        "applies_if": applies_if if applies_if is not None else {},
    }
    if min_amount is not None: defaults["min_amount"] = min_amount
    if max_amount is not None: defaults["max_amount"] = max_amount
    if percent_of_code is not None: defaults["percent_of_code"] = percent_of_code
    if per_kg_threshold is not None: defaults["per_kg_threshold"] = per_kg_threshold
    RatecardFees.objects.update_or_create(
        ratecard_id=rc.id, fee_type_id=ft.id, defaults=defaults
    )

def add_service_item(rc, service_code, currency, amount, *, min_amount=None, max_amount=None, tax_pct=0, percent_of_service_code=None):
    svc = Services.objects.get(code=service_code)
    defaults = {"currency": currency, "amount": amount, "tax_pct": tax_pct, "conditions_json": {}}
    if min_amount is not None: defaults["min_amount"] = min_amount
    if max_amount is not None: defaults["max_amount"] = max_amount
    if percent_of_service_code is not None: defaults["percent_of_service_code"] = percent_of_service_code
    return ServiceItems.objects.update_or_create(
        ratecard_id=rc.id, service_id=svc.id, defaults=defaults
    )[0]

def add_sell_cost_link(sell_item, buy_fee_code, mapping_type, mapping_value=None):
    """(NEW) Helper to create SellCostLinksSimple records."""
    ft = FeeTypes.objects.get(code=buy_fee_code)
    SellCostLinksSimple.objects.update_or_create(
        sell_item=sell_item,
        buy_fee_code=ft,
        defaults={
            "mapping_type": mapping_type,
            "mapping_value": mapping_value,
        },
    )


def ensure_fx(base, quote, rate, source="manual"):
    CurrencyRates.objects.update_or_create(
        base_ccy=base.upper(),
        quote_ccy=quote.upper(),
        defaults={"rate": rate, "as_of_ts": now(), "source": source},
    )

def ensure_policy(audience, *, caf_on_fx=True, gst_applies=True, gst_pct=10):
    PricingPolicy.objects.update_or_create(
        audience=audience,
        defaults={"caf_on_fx": caf_on_fx, "gst_applies": gst_applies, "gst_pct": gst_pct}
    )
#endregion

#region -------- Seeding Functions --------
@transaction.atomic
def seed_airports_and_providers():
    """Seeds core airports and providers."""
    upsert_station("POM", "Port Moresby", "PG")
    upsert_station("LAE", "Lae", "PG")
    upsert_station("BNE", "Brisbane", "AU")
    upsert_station("SYD", "Sydney", "AU")
    upsert_station("SIN", "Singapore", "SG")
    upsert_station("HKG", "Hong Kong", "HK")

    upsert_provider("Air Niugini", "CARRIER")
    upsert_provider("Qantas Freight", "CARRIER")
    upsert_provider("Maersk Air Freight", "AGENT")

@transaction.atomic
def seed_fee_types_and_services():
    """Seeds the global catalogue of BUY-side fee types and SELL-side services."""
    ensure_fee_type("X_RAY", "Mandatory X-Ray Screening", "PER_KG")
    ensure_fee_type("CTO", "Cargo Terminal Operator (Terminal Fee)", "PER_KG")
    ensure_fee_type("FUEL", "Fuel Surcharge", "PER_KG")
    ensure_fee_type("SECURITY", "Security Surcharge", "PER_KG")
    ensure_fee_type("FREIGHT", "Base Air Freight", "PER_KG") # For linking pass-through freight

    ensure_service("CLEARANCE_EXP", "Export Customs Clearance", "PER_SHIPMENT")
    ensure_service("CLEARANCE_IMP", "Import Customs Clearance", "PER_SHIPMENT")
    ensure_service("CARTAGE_POM", "Cartage - POM Metro", "PER_KG")
    ensure_service("FUEL_LEVY", "Fuel Levy", "PERCENT_OF")
    ensure_service("AIR_FREIGHT", "Air Freight Charge", "PER_KG") # Customer-facing freight line

@transaction.atomic
def seed_buy_bne_pom_aud():
    """Seeds a realistic BUY rate card for BNE -> POM in AUD."""
    bne = Stations.objects.get(iata="BNE")
    pom = Stations.objects.get(iata="POM")
    efm = Providers.objects.get(name="Maersk Air Freight")

    rc = ensure_ratecard(
        provider=efm, name="EFM AU->POM BUY (AUD)",
        role="BUY", scope="INTERNATIONAL", direction="EXPORT", currency="AUD",
    )
    ensure_lane_with_breaks(
        rc, origin=bne, dest=pom, airline="NU", is_direct=True,
        breaks=[
            {"code": "MIN", "min": 330.00}, {"code": "45", "kg": 7.05},
            {"code": "100", "kg": 6.75}, {"code": "250", "kg": 6.55},
            {"code": "500", "kg": 6.25}, {"code": "1000", "kg": 5.95},
        ]
    )
    add_fee(rc, "X_RAY", "AUD", "0.36", min_amount="70.00")
    add_fee(rc, "CTO", "AUD", "0.30", min_amount="30.00")

@transaction.atomic
def seed_buy_pom_sin_usd():
    """Seeds a realistic BUY rate card for POM -> SIN in USD."""
    pom = Stations.objects.get(iata="POM")
    sin = Stations.objects.get(iata="SIN")
    agent = Providers.objects.get(name="Maersk Air Freight")

    rc = ensure_ratecard(
        provider=agent, name="Agent POM->SIN BUY (USD)",
        role="BUY", scope="INTERNATIONAL", direction="EXPORT", currency="USD",
    )
    ensure_lane_with_breaks(
        rc, origin=pom, dest=sin, airline="NU", is_direct=False,
        breaks=[
            {"code": "MIN", "min": 190.00}, {"code": "45", "kg": 7.19},
            {"code": "100", "kg": 6.90}, {"code": "250", "kg": 6.60},
            {"code": "500", "kg": 6.40}, {"code": "1000", "kg": 6.20},
        ]
    )
    add_fee(rc, "FUEL", "USD", "0.56")
    add_fee(rc, "SECURITY", "USD", "0.143")

@transaction.atomic
def seed_buy_pom_lae_pgk():
    """Seeds a domestic BUY rate card for POM -> LAE."""
    pom = Stations.objects.get(iata="POM")
    lae = Stations.objects.get(iata="LAE")
    px = Providers.objects.get(name="Air Niugini")

    rc = ensure_ratecard(
        provider=px, name="Air Niugini Domestic BUY (PGK)",
        role="BUY", scope="DOMESTIC", direction="EXPORT", currency="PGK",
    )
    ensure_lane_with_breaks(
        rc, origin=pom, dest=lae, airline="PX", is_direct=True,
        breaks=[
            {"code": "MIN", "min": 150.00},
            {"code": "100", "kg": 2.50},
            {"code": "500", "kg": 2.20},
        ]
    )
    add_fee(rc, "SECURITY", "PGK", "0.20", min_amount="25.00")

@transaction.atomic
def seed_sell_pgk_export():
    """Seeds a PGK Export SELL Menu for local customers."""
    our_company = Providers.objects.get(name="Maersk Air Freight")

    rc = ensure_ratecard(
        provider=our_company, name="PGK Export SELL Menu",
        role="SELL", scope="INTERNATIONAL", direction="EXPORT",
        currency="PGK", audience="PGK_LOCAL",
    )
    add_service_item(rc, "CLEARANCE_EXP", "PGK", "350.00")
    add_service_item(rc, "CARTAGE_POM", "PGK", "0.80", min_amount="120.00", tax_pct="10.0")
    add_service_item(rc, "FUEL_LEVY", "PGK", "0.15", percent_of_service_code="CARTAGE_POM", tax_pct="10.0")
    # This is our main sellable freight service
    add_service_item(rc, "AIR_FREIGHT", "PGK", "0.0") # Price will be set by link mapping

@transaction.atomic
def seed_sell_pgk_import():
    """Seeds a PGK Import SELL Menu for local customers."""
    our_company = Providers.objects.get(name="Maersk Air Freight")

    rc = ensure_ratecard(
        provider=our_company, name="PGK Import SELL Menu",
        role="SELL", scope="INTERNATIONAL", direction="IMPORT",
        currency="PGK", audience="PGK_LOCAL",
    )
    add_service_item(rc, "CLEARANCE_IMP", "PGK", "450.00", min_amount="450.00")
    add_service_item(rc, "CARTAGE_POM", "PGK", "0.85", min_amount="150.00", tax_pct="10.0")
    add_service_item(rc, "FUEL_LEVY", "PGK", "0.15", percent_of_service_code="CARTAGE_POM", tax_pct="10.0")
    add_service_item(rc, "AIR_FREIGHT", "PGK", "0.0")


@transaction.atomic
def seed_sell_cost_links():
    """(NEW) Seeds the links between SELL items and their underlying BUY costs."""
    # Get the SELL rate cards and their items
    export_rc = Ratecards.objects.get(name="PGK Export SELL Menu")
    import_rc = Ratecards.objects.get(name="PGK Import SELL Menu")

    exp_freight_item = ServiceItems.objects.get(ratecard=export_rc, service__code="AIR_FREIGHT")
    imp_freight_item = ServiceItems.objects.get(ratecard=import_rc, service__code="AIR_FREIGHT")

    # --- Mapping Rule 1: Pass-Through Freight ---
    # The customer freight charge is the sum of underlying BUY freight costs, passed through.
    add_sell_cost_link(exp_freight_item, "FREIGHT", "PASS_THROUGH")
    add_sell_cost_link(imp_freight_item, "FREIGHT", "PASS_THROUGH")

    # --- Mapping Rule 2: Cost-Plus Markup ---
    # We can also link other surcharges with a markup.
    # Example: Link the SELL freight item to the BUY fuel cost and add a 10% margin.
    add_sell_cost_link(exp_freight_item, "FUEL", "COST_PLUS_PCT", mapping_value="0.10")
    add_sell_cost_link(imp_freight_item, "FUEL", "COST_PLUS_PCT", mapping_value="0.10")

    # Example: Pass through the security cost directly with no markup.
    add_sell_cost_link(exp_freight_item, "SECURITY", "PASS_THROUGH")
    add_sell_cost_link(imp_freight_item, "SECURITY", "PASS_THROUGH")


@transaction.atomic
def seed_fx_and_policy():
    """Seeds exchange rates and pricing policies."""
    ensure_fx("AUD", "PGK", "2.45")
    ensure_fx("USD", "PGK", "3.65")
    ensure_policy("PGK_LOCAL", caf_on_fx=True, gst_applies=True, gst_pct=10)
    ensure_policy("AUD_AGENT", caf_on_fx=False, gst_applies=False, gst_pct=0)
    ensure_policy("USD_AGENT", caf_on_fx=False, gst_applies=False, gst_pct=0)

#endregion

class Command(BaseCommand):
    help = "Seeds the database with a realistic sandbox dataset for the RateEngine."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Seeding realistic sandbox data..."))

        # Core data
        seed_airports_and_providers()
        seed_fee_types_and_services()

        # BUY rate cards
        seed_buy_bne_pom_aud()
        seed_buy_pom_sin_usd()
        seed_buy_pom_lae_pgk()

        # SELL rate cards (Menus)
        seed_sell_pgk_export()
        seed_sell_pgk_import()

        # Link SELL items to BUY costs
        seed_sell_cost_links() # New

        # Financials
        seed_fx_and_policy()

        self.stdout.write(self.style.SUCCESS("Sandbox data has been seeded successfully."))
