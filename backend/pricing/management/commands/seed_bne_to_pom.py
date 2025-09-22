from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from decimal import Decimal

from organizations.models import Organizations

from pricing.management.commands.seed_initial_data import (
    add_fee,
    add_sell_cost_link,
    add_service_item,
    ensure_fee_type,
    ensure_lane_with_breaks,
    ensure_ratecard,
    ensure_policy,
    ensure_service,
    upsert_provider,
    upsert_station,
)
from pricing.models import (
    Ratecards,
    RatecardFees,
    Routes,
    RouteLegs,
    SellCostLinksSimple,
    ServiceItems,
    PricingPolicy,
)




class Command(BaseCommand):
    help = "Seed realistic AUD BUY data for BNE/SYD -> POM (door-to-airport) and map SELL pass-through pricing."

    def add_arguments(self, parser):
        parser.add_argument("--provider", default="Maersk Air Freight")
        parser.add_argument("--ratecard-bne", default="EFM BNE->POM BUY (AUD)")
        parser.add_argument("--ratecard-syd", default="EFM SYD->POM BUY (AUD)")
        parser.add_argument("--ratecard-syd-via", default="EFM SYD->POM via BNE BUY (AUD)")
        parser.add_argument("--sell-ratecard", default="AUD Import SELL Menu")

    @transaction.atomic
    def handle(self, *args, **options):
        # Load data from JSON file
        from pathlib import Path
        import json
        
        data_path = Path(__file__).resolve().parent / 'data' / 'seed_bne_to_pom_data.json'
        with open(data_path, 'r') as f:
            seed_data = json.load(f)

        LANE_BREAKS_BNE = seed_data['lane_breaks_bne']
        LANE_BREAKS_SYD_DIRECT = seed_data['lane_breaks_syd_direct']
        LANE_BREAKS_SYD_VIA = seed_data['lane_breaks_syd_via']
        BUY_FEE_DEFS = seed_data['buy_fee_defs']
        SELL_SERVICE_DEFS = seed_data['sell_service_defs']
        SELL_LINKS = seed_data['sell_links']
        LEGACY_NAMES = seed_data['legacy_names']

        provider_name = options["provider"]
        ratecard_bne = options["ratecard_bne"]
        ratecard_syd = options["ratecard_syd"]
        ratecard_syd_via = options["ratecard_syd_via"]
        sell_ratecard_name = options["sell_ratecard"]

        self.stdout.write(self.style.WARNING("Ensuring foundational records..."))
        PricingPolicy.objects.filter(audience="AU_AGENT_PREPAID").delete()
        bne = upsert_station("BNE", "Brisbane", "AU")
        syd = upsert_station("SYD", "Sydney", "AU")
        pom = upsert_station("POM", "Port Moresby", "PG")
        provider = upsert_provider(provider_name, "AGENT")

        for code, desc, basis, _ in BUY_FEE_DEFS:
            ensure_fee_type(code, desc, basis)
        for code, desc, basis, _ in SELL_SERVICE_DEFS:
            ensure_service(code, desc, basis)

        self.stdout.write(self.style.WARNING("Retiring legacy AU->POM ratecards..."))
        Ratecards.objects.filter(name__in=LEGACY_NAMES).update(
            status="RETIRED",
            expiry_date=now().date() - timedelta(days=1),
        )

        self.stdout.write(self.style.WARNING("Creating BUY ratecards and lanes..."))
        bne_rc = ensure_ratecard(provider, ratecard_bne, "BUY", "INTERNATIONAL", "EXPORT", "AUD")
        ensure_lane_with_breaks(bne_rc, bne, pom, airline="NU", is_direct=True, breaks=LANE_BREAKS_BNE)

        syd_rc = ensure_ratecard(provider, ratecard_syd, "BUY", "INTERNATIONAL", "EXPORT", "AUD")
        ensure_lane_with_breaks(syd_rc, syd, pom, airline="NU", is_direct=True, breaks=LANE_BREAKS_SYD_DIRECT)

        syd_via_rc = ensure_ratecard(provider, ratecard_syd_via, "BUY", "INTERNATIONAL", "EXPORT", "AUD")
        ensure_lane_with_breaks(syd_via_rc, syd, pom, airline="NU", is_direct=False, breaks=LANE_BREAKS_SYD_VIA, via=bne)

        self.stdout.write(self.style.WARNING("Attaching BUY surcharges..."))
        allowed_buy_codes = {code for code, *_ in BUY_FEE_DEFS}
        for rc in (bne_rc, syd_rc, syd_via_rc):
            RatecardFees.objects.filter(ratecard=rc).exclude(
                fee_type__code__in=allowed_buy_codes
            ).delete()
            for code, _desc, _basis, params in BUY_FEE_DEFS:
                add_fee(
                    rc,
                    code,
                    "AUD",
                    params["amount"],
                    min_amount=params.get("min_amount"),
                    max_amount=params.get("max_amount"),
                    applies_if=params.get("applies_if"),
                    percent_of_code=params.get("percent_of_code"),
                )

        self.stdout.write(self.style.WARNING("Ensuring route configuration for auto-rating..."))
        route, _ = Routes.objects.get_or_create(
            origin_country="AU",
            dest_country="PG",
            shipment_type="IMPORT",
            defaults={
                "name": "AU->PG",
                "requires_manual_rate": False,
            },
        )
        if route.requires_manual_rate:
            route.requires_manual_rate = False
            route.save(update_fields=["requires_manual_rate"])

        RouteLegs.objects.update_or_create(
            route=route,
            sequence=1,
            defaults={
                "origin": bne,
                "dest": pom,
                "leg_scope": "INTERNATIONAL",
                "service_type": "LINEHAUL",
            },
        )

        RouteLegs.objects.update_or_create(
            route=route,
            sequence=2,
            defaults={
                "origin": syd,
                "dest": pom,
                "leg_scope": "INTERNATIONAL",
                "service_type": "LINEHAUL",
            },
        )

        self.stdout.write(self.style.WARNING("Configuring SELL menu for AUD importers..."))
#        ensure_policy("AU_AGENT_PREPAID", gst_applies=False, gst_pct=0)
        sell_rc = ensure_ratecard(
            provider,
            sell_ratecard_name,
            "SELL",
            "INTERNATIONAL",
            "IMPORT",
            "AUD",
            audience="AUD_AGENT",
        )

        allowed_sell_codes = {code for code, *_ in SELL_SERVICE_DEFS}

        SellCostLinksSimple.objects.filter(sell_item__ratecard=sell_rc).exclude(
            sell_item__service__code__in=allowed_sell_codes
        ).delete()
        ServiceItems.objects.filter(ratecard=sell_rc).exclude(
            service__code__in=allowed_sell_codes
        ).delete()

        sell_items = {}
        for code, desc, basis, extra in SELL_SERVICE_DEFS:
            item = add_service_item(
                sell_rc,
                code,
                "AUD",
                "0.00",
                percent_of_service_code=extra.get("percent_of_service_code"),
            )
            sell_items[code] = item

        for service_code, buy_code, mapping_type, mapping_value in SELL_LINKS:
            add_sell_cost_link(
                sell_items[service_code],
                buy_code,
                mapping_type,
                mapping_value,
            )

        self.stdout.write(self.style.WARNING("Aligning Australian importer org profile..."))
        org = Organizations.objects.filter(name="AU Importer Pty Ltd").first()
        if org:
            updated_fields = []
            if org.audience != "AUD_AGENT":
                org.audience = "AUD_AGENT"
                updated_fields.append("audience")
            if org.default_sell_currency != "AUD":
                org.default_sell_currency = "AUD"
                updated_fields.append("default_sell_currency")
            if updated_fields:
                org.save(update_fields=updated_fields)
                self.stdout.write(self.style.SUCCESS("Updated AU Importer Pty Ltd audience/currency."))

        self.stdout.write(self.style.SUCCESS("BNE/SYD -> POM BUY and AUD SELL data seeded successfully."))
