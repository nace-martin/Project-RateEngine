from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    Currency,
    Country,
    City,
    Airport,
    Policy,
    FxSnapshot,
)
from parties.models import Company, Contact, CustomerCommercialProfile
from services.models import (
    ServiceComponent,
    ServiceRule,
    ServiceRuleComponent,
)
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal


SERVICE_COMPONENT_DEFS = [
    {
        "code": "AIR_FREIGHT_SEED",
        "description": "Air Freight (BNE → POM)",
        "mode": "AIR",
        "leg": "MAIN",
        "category": "TRANSPORT",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "FCY",
        "unit": "KG",
        "tax_rate": Decimal("0.00"),
    },
    {
        "code": "ORIGIN_PICKUP_SEED",
        "description": "Origin Pickup (Metro AU)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "LOCAL",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "FCY",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "ORIGIN_FUEL_SURCH_SEED",
        "description": "Origin Fuel Surcharge",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "ACCESSORIAL",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("70.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
        "tiering_json": {"percent_of": "ORIGIN_PICKUP_SEED", "percent": "0.20"},
    },
    {
        "code": "ORIGIN_SECURITY_SEED",
        "description": "Origin Security Screening",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "STATUTORY",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("55.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "IMPORT_HANDLING_SEED",
        "description": "Import Handling (POM)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("180.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "IMPORT_CLEARANCE_SEED",
        "description": "Import Customs Clearance",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "CUSTOMS",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("320.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.00"),
    },
]


PNG_LOCAL_COMPONENT_DEFS = [
    {
        "code": "CUS_CLR_IMP",
        "description": "Customs Clearance (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "CUSTOMS",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.00"),
    },
    {
        "code": "AGENCY_IMP",
        "description": "Agency Fee (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "DOC_IMP",
        "description": "Documentation Fee (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "DOCUMENTATION",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "HANDLING_GEN",
        "description": "Handling Fee - General (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "TERM_INT_IMP",
        "description": "International Terminal Fee (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "CARTAGE_IMP",
        "description": "Cartage & Delivery (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "LOCAL",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "KG",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "CARTAGE_FUEL_IMP",
        "description": "Fuel Surcharge - Cartage (Import)",
        "mode": "AIR",
        "leg": "DESTINATION",
        "category": "ACCESSORIAL",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
        "tiering_json": {"percent_of": "CARTAGE_IMP", "percent": "0.10"},
    },
    {
        "code": "FUEL_SUR_AIR",
        "description": "Fuel Surcharge - Air",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "ACCESSORIAL",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "SEC_SUR_AIR",
        "description": "Security Surcharge - Air",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "STATUTORY",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "AWB_FEE",
        "description": "Airwaybill Fee",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "DOCUMENTATION",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "DOC_EXP",
        "description": "Documentation Fee (Export)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "DOCUMENTATION",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "BUILD_UP_FEE",
        "description": "Build-Up Fee",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "TERM_INT_EXP",
        "description": "International Terminal Fee (Export)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "CUS_CLR_EXP",
        "description": "Customs Clearance (Export)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "CUSTOMS",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.00"),
    },
    {
        "code": "AGENCY_EXP",
        "description": "Agency Fee (Export)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "HANDLING",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "DOM_ONFWD",
        "description": "Domestic Onforwarding",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "LOCAL",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "KG",
        "tax_rate": Decimal("0.10"),
    },
    {
        "code": "PKUP_ORG",
        "description": "Pickup / Cartage (Origin)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "LOCAL",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "KG",
        "tax_rate": Decimal("0.10"),
        "min_charge_pgk": Decimal("50.00"),
    },
    {
        "code": "CARTAGE_FUEL_EXP",
        "description": "Fuel Surcharge - Cartage (Export)",
        "mode": "AIR",
        "leg": "ORIGIN",
        "category": "ACCESSORIAL",
        "cost_type": "COGS",
        "cost_source": "BASE_COST",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "PGK",
        "unit": "SHIPMENT",
        "tax_rate": Decimal("0.10"),
        "tiering_json": {"percent_of": "PKUP_ORG", "percent": "0.10"},
    },
    {
        "code": "FRT_AIR",
        "description": "Air Freight (Linehaul)",
        "mode": "AIR",
        "leg": "MAIN",
        "category": "TRANSPORT",
        "cost_type": "COGS",
        "cost_source": "PARTNER_RATECARD",
        "base_pgk_cost": Decimal("0.00"),
        "cost_currency_type": "FCY",
        "unit": "KG",
        "tax_rate": Decimal("0.00"),
    },
]


PARTNER_RATE_DEFS = [
    {
        "component_code": "AIR_FREIGHT_SEED",
        "unit": "KG",
        "rate_per_kg_fcy": Decimal("4.20"),
        "min_charge_fcy": Decimal("0.00"),
    },
    {
        "component_code": "ORIGIN_PICKUP_SEED",
        "unit": "SHIPMENT",
        "rate_per_shipment_fcy": Decimal("150.00"),
        "min_charge_fcy": Decimal("150.00"),
    },
]


PNG_LOCAL_IMPORT_RATE_DEFS = [
    {
        "component_code": "CUS_CLR_IMP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("300.00"),
    },
    {
        "component_code": "AGENCY_IMP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("250.00"),
    },
    {
        "component_code": "DOC_IMP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("100.00"),
    },
    {
        "component_code": "HANDLING_GEN",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("100.00"),
    },
    {
        "component_code": "TERM_INT_IMP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("100.00"),
    },
    {
        "component_code": "CARTAGE_IMP",
        "unit": "KG",
        "rate_per_kg_pgk": Decimal("0.80"),
        "min_charge_pgk": Decimal("80.00"),
    },
    {
        "component_code": "DOM_ONFWD",
        "unit": "KG",
        "rate_per_kg_pgk": Decimal("2.50"),
    },
]


PNG_LOCAL_EXPORT_RATE_DEFS = [
    {
        "component_code": "AWB_FEE",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("50.00"),
    },
    {
        "component_code": "DOC_EXP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("50.00"),
    },
    {
        "component_code": "CUS_CLR_EXP",
        "unit": "SHIPMENT",
        "rate_per_shipment_pgk": Decimal("250.00"),
    },
    {
        "component_code": "PKUP_ORG",
        "unit": "KG",
        "rate_per_kg_pgk": Decimal("0.50"),
        "min_charge_pgk": Decimal("50.00"),
    },
]


SERVICE_RULE_DEFS = [
    {
        "mode": "AIR",
        "direction": "IMPORT",
        "incoterm": "EXW",
        "payment_term": "PREPAID",
        "service_scope": "D2D",
        "description": "Seed AIR IMPORT EXW Door-to-Door",
        "components": [
            {"code": "ORIGIN_PICKUP_SEED"},
            {"code": "ORIGIN_FUEL_SURCH_SEED"},
            {"code": "ORIGIN_SECURITY_SEED"},
            {"code": "AIR_FREIGHT_SEED"},
            {"code": "IMPORT_HANDLING_SEED"},
            {"code": "IMPORT_CLEARANCE_SEED"},
        ],
    },
    {
        "mode": "AIR",
        "direction": "IMPORT",
        "incoterm": "EXW",
        "payment_term": "PREPAID",
        "service_scope": "D2A",
        "description": "Seed AIR IMPORT EXW Door-to-Airport",
        "components": [
            {"code": "ORIGIN_PICKUP_SEED"},
            {"code": "ORIGIN_FUEL_SURCH_SEED"},
            {"code": "ORIGIN_SECURITY_SEED"},
            {"code": "AIR_FREIGHT_SEED"},
        ],
    },
    {
        "mode": "AIR",
        "direction": "IMPORT",
        "incoterm": "EXW",
        "payment_term": "PREPAID",
        "service_scope": "A2D",
        "description": "Seed AIR IMPORT EXW Airport-to-Door",
        "components": [
            {"code": "AIR_FREIGHT_SEED"},
            {"code": "IMPORT_HANDLING_SEED"},
            {"code": "IMPORT_CLEARANCE_SEED"},
        ],
    },
    {
        "mode": "AIR",
        "direction": "IMPORT",
        "incoterm": "EXW",
        "payment_term": "PREPAID",
        "service_scope": "A2A",
        "description": "Seed AIR IMPORT EXW Airport-to-Airport",
        "components": [
            {"code": "AIR_FREIGHT_SEED"},
        ],
    },
    {
        "mode": "AIR",
        "direction": "IMPORT",
        "incoterm": "DAP",
        "payment_term": "COLLECT",
        "service_scope": "A2D",
        "description": "Import Collect DAP A2D (Hybrid)",
        "components": [
            {"code": "CUS_CLR_IMP"},
            {"code": "AGENCY_IMP"},
            {"code": "DOC_IMP"},
            {"code": "HANDLING_GEN"},
            {"code": "TERM_INT_IMP"},
            {"code": "CARTAGE_IMP"},
            {"code": "CARTAGE_FUEL_IMP"},
        ],
    },
    {
        "mode": "AIR",
        "direction": "EXPORT",
        "incoterm": "CPT",
        "payment_term": "PREPAID",
        "service_scope": "D2A",
        "description": "Export Prepaid CPT D2A (Hybrid)",
        "components": [
            {"code": "PKUP_ORG"},
            {"code": "CARTAGE_FUEL_EXP"},
            {"code": "CUS_CLR_EXP"},
            {"code": "AGENCY_EXP"},
            {"code": "DOC_EXP"},
            {"code": "AWB_FEE"},
            {"code": "SEC_SUR_AIR"},
            {"code": "FUEL_SUR_AIR"},
            {"code": "TERM_INT_EXP"},
            {"code": "FRT_AIR"},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed a minimal but complete dataset so the V3 quote compute flow can run end-to-end."

    def handle(self, *args, **options):
        self.stdout.write("Cleaning V3 data...")
        QuoteLine.objects.all().delete()
        QuoteTotal.objects.all().delete()
        QuoteVersion.objects.all().delete()
        Quote.objects.all().delete()
        ServiceRule.objects.all().delete()
        ServiceComponent.objects.all().delete()
        PartnerRate.objects.all().delete()

        with transaction.atomic():
            currencies = self._ensure_currencies()
            countries, cities, airports = self._ensure_locations()
            customer, contact, supplier = self._ensure_parties(countries["PG"], currencies["PGK"])
            policy = self._ensure_policy()
            snapshot = self._ensure_fx_snapshot()
            components = self._ensure_service_components()
            components.update(self._ensure_png_local_service_components())
            self._ensure_service_rules(components)
            partner_lanes = self._ensure_partner_rates(
                supplier=supplier,
                lanes=[
                    (airports["BNE"], airports["POM"]),
                ],
                components=components,
            )
            lane = partner_lanes[0]
            png_local_lane = self._ensure_png_import_local_rates(
                origin=airports["BNE"],
                destination=airports["POM"],
                components=components,
            )
            png_export_lane = self._ensure_png_export_local_rates(
                origin=airports["POM"],
                destination=airports["BNE"],
                components=components,
            )

            self.stdout.write(self.style.SUCCESS("V3 compute seed complete"))
            self.stdout.write(f"  - Customer: {customer.name} (contact: {contact.email})")
            self.stdout.write(f"  - Supplier: {supplier.name}")
            self.stdout.write(f"  - Policy: {policy.name}")
            self.stdout.write(f"  - FX Snapshot: {snapshot.as_of_timestamp.isoformat()}")
            self.stdout.write(f"  - Partner lane: {lane.origin_airport_id} -> {lane.destination_airport_id}")
            if png_local_lane:
                self.stdout.write(
                    f"  - PNG import locals: {png_local_lane.rate_card.name} "
                    f"({png_local_lane.origin_airport_id}->{png_local_lane.destination_airport_id})"
                )
            if png_export_lane:
                self.stdout.write(
                    f"  - PNG export locals: {png_export_lane.rate_card.name} "
                    f"({png_export_lane.origin_airport_id}->{png_export_lane.destination_airport_id})"
                )

    def _ensure_currencies(self):
        data = {
            "PGK": {"name": "Papua New Guinea Kina", "minor_units": 2},
            "AUD": {"name": "Australian Dollar", "minor_units": 2},
        }
        objects = {}
        for code, defaults in data.items():
            obj, _ = Currency.objects.get_or_create(code=code, defaults=defaults)
            objects[code] = obj
        return objects

    def _ensure_locations(self):
        countries = {}
        for code, name in [("PG", "Papua New Guinea"), ("AU", "Australia")]:
            country, _ = Country.objects.get_or_create(code=code, defaults={"name": name})
            countries[code] = country

        cities = {}
        city_defs = [
            ("Port Moresby", countries["PG"]),
            ("Brisbane", countries["AU"]),
        ]
        for name, country in city_defs:
            city, _ = City.objects.get_or_create(name=name, country=country)
            cities[name] = city

        airports = {}
        airport_defs = {
            "POM": {"name": "Port Moresby Jacksons Intl", "city": cities["Port Moresby"]},
            "BNE": {"name": "Brisbane Intl", "city": cities["Brisbane"]},
        }
        for code, defaults in airport_defs.items():
            airport, created = Airport.objects.get_or_create(iata_code=code, defaults=defaults)
            if not created and defaults.get("city") and airport.city_id is None:
                airport.city = defaults["city"]
                airport.save(update_fields=["city"])
            airports[code] = airport

        return countries, cities, airports

    def _ensure_parties(self, png_country, default_currency):
        customer, _ = Company.objects.get_or_create(
            name="Seed Customer Pty Ltd",
            defaults={"is_customer": True},
        )
        contact, _ = Contact.objects.get_or_create(
            company=customer,
            email="seed.customer@example.com",
            defaults={"first_name": "Seed", "last_name": "Customer"},
        )

        CustomerCommercialProfile.objects.get_or_create(
            company=customer,
            defaults={
                "preferred_quote_currency": default_currency,
                "default_margin_percent": Decimal("20.00"),
            },
        )

        supplier, _ = Company.objects.get_or_create(
            name="Seed Carrier Ltd",
            defaults={"is_agent": True, "is_carrier": True},
        )

        return customer, contact, supplier

    def _ensure_self_supplier(self):
        supplier, _ = Company.objects.get_or_create(
            name="Self",
            defaults={"is_agent": True},
        )
        return supplier

    def _ensure_policy(self):
        policy, created = Policy.objects.get_or_create(
            name="Seed Default Policy",
            defaults={
                "caf_import_pct": Decimal("0.05"),
                "caf_export_pct": Decimal("0.05"),
                "margin_pct": Decimal("0.20"),
                "effective_from": timezone.now(),
                "is_active": True,
            },
        )
        if not created and not policy.is_active:
            policy.is_active = True
            policy.save(update_fields=["is_active"])
        return policy

    def _ensure_fx_snapshot(self):
        snapshot = FxSnapshot.objects.filter(source="seed_v3").order_by("-as_of_timestamp").first()
        if snapshot:
            return snapshot

        return FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="seed_v3",
            rates={
                "AUD": {"tt_buy": "2.40", "tt_sell": "2.30"},
                "USD": {"tt_buy": "3.40", "tt_sell": "3.30"},
            },
            caf_percent=Decimal("0.02"),
            fx_buffer_percent=Decimal("0.01"),
        )

    def _ensure_service_components(self):
        return self._upsert_service_components(SERVICE_COMPONENT_DEFS)

    def _ensure_png_local_service_components(self):
        return self._upsert_service_components(PNG_LOCAL_COMPONENT_DEFS)

    def _upsert_service_components(self, definitions):
        components = {}
        for definition in definitions:
            lookup = {"code": definition["code"]}
            defaults = {key: val for key, val in definition.items() if key != "code"}
            component, created = ServiceComponent.objects.get_or_create(**lookup, defaults=defaults)
            if not created:
                updated_fields = []
                for field, value in defaults.items():
                    if getattr(component, field) != value:
                        setattr(component, field, value)
                        updated_fields.append(field)
                if updated_fields:
                    component.save(update_fields=updated_fields)
            components[definition["code"]] = component
        return components

    def _ensure_service_rules(self, components):
        recipes = {
            "AIR_EXPORT_D2A_COLLECT_CPT_AGENT": {
                "mode": "AIR",
                "direction": "EXPORT",
                "incoterm": "CPT",
                "payment_term": "COLLECT",
                "service_scope": "D2A",
                "description": "Agent Request: Export to Agent (USD), we handle Origin + Freight.",
                "output_currency_type": "USD",
                "components": [
                    {"code": "PKUP_ORG"},
                    {"code": "CUS_CLR_EXP"},
                    {"code": "DOC_EXP"},
                    {"code": "FRT_AIR"},
                    {"code": "AWB_FEE"},
                    {"code": "SEC_SUR_AIR"},
                ],
            },
            "AIR_EXPORT_D2D_COLLECT_EXW_FULL": {
                "mode": "AIR",
                "direction": "EXPORT",
                "incoterm": "EXW",
                "payment_term": "COLLECT",
                "service_scope": "D2D",
                "description": "Export Full D2D (PGK): Auto Origin + Manual Frt/Dest.",
                "output_currency_type": "PGK",
                "components": [
                    {"code": "PKUP_ORG"},
                    {"code": "CARTAGE_FUEL_EXP"},
                    {"code": "CUS_CLR_EXP"},
                    {"code": "AGENCY_EXP"},
                    {"code": "DOC_EXP"},
                    {"code": "AWB_FEE"},
                    {"code": "SEC_SUR_AIR"},
                    {"code": "FUEL_SUR_AIR"},
                    {"code": "TERM_INT_EXP"},
                    {"code": "FRT_AIR", "notes": "Manual International Freight"},
                    {"code": "CUS_CLR_IMP", "notes": "Manual Destination Clearance"},
                    {"code": "CARTAGE_IMP", "notes": "Manual Destination Delivery"},
                ],
            },
            "AIR_IMPORT_A2D_PREPAID_DAP_AGENT": {
                "mode": "AIR",
                "direction": "IMPORT",
                "incoterm": "DAP",
                "payment_term": "PREPAID",
                "service_scope": "A2D",
                "description": "Agent Request: Import from Agent (USD), we handle Dest only.",
                "output_currency_type": "USD",
                "components": [
                    {"code": "CUS_CLR_IMP"},
                    {"code": "DOC_IMP"},
                    {"code": "HANDLING_GEN"},
                    {"code": "CARTAGE_IMP"},
                ],
            },
            "AIR_IMPORT_A2D_COLLECT_DAP_LOCAL": {
                "mode": "AIR",
                "direction": "IMPORT",
                "incoterm": "DAP",
                "payment_term": "COLLECT",
                "service_scope": "A2D",
                "description": "Local Client: Import DAP (PGK), we handle Dest only.",
                "output_currency_type": "PGK",
                "components": [
                    {"code": "CUS_CLR_IMP"},
                    {"code": "DOC_IMP"},
                    {"code": "HANDLING_GEN"},
                    {"code": "CARTAGE_IMP"},
                ],
            },
            "AIR_IMPORT_D2D_COLLECT_EXW_FULL": {
                "mode": "AIR",
                "direction": "IMPORT",
                "incoterm": "EXW",
                "payment_term": "COLLECT",
                "service_scope": "D2D",
                "description": "Full Import (PGK): Manual Origin/Freight + Auto Dest.",
                "output_currency_type": "PGK",
                "components": [
                    {"code": "PKUP_ORG", "notes": "Manual Origin Pickup"},
                    {"code": "CUS_CLR_EXP", "notes": "Manual Export Clearance"},
                    {"code": "FRT_AIR", "notes": "Manual International Freight"},
                    {"code": "CUS_CLR_IMP"},
                    {"code": "DOC_IMP"},
                    {"code": "CARTAGE_IMP"},
                ],
            },
            "AIR_IMPORT_D2A_COLLECT_EXW_ONFWD": {
                "mode": "AIR",
                "direction": "IMPORT",
                "incoterm": "EXW",
                "payment_term": "COLLECT",
                "service_scope": "D2A",
                "description": "Import to HGU (No Deliv): Manual Orig/Frt + POM Transit + Dom Frt.",
                "output_currency_type": "PGK",
                "components": [
                    {"code": "PKUP_ORG", "notes": "Manual Origin Pickup"},
                    {"code": "FRT_AIR", "notes": "Manual International Freight"},
                    {"code": "CUS_CLR_IMP"},
                    {"code": "DOM_ONFWD"},
                ],
            },
        }

        all_rules = SERVICE_RULE_DEFS + list(recipes.values())
        for rule_def in all_rules:
            filters = {
                "mode": rule_def["mode"],
                "direction": rule_def["direction"],
                "incoterm": rule_def.get("incoterm"),
                "payment_term": rule_def["payment_term"],
                "service_scope": rule_def["service_scope"],
            }
            defaults = {
                "description": rule_def.get("description", ""),
                "output_currency_type": rule_def.get("output_currency_type", "DESTINATION"),
                "notes": rule_def.get("notes", ""),
            }
            rule, created = ServiceRule.objects.get_or_create(defaults=defaults, **filters)
            if not created:
                updated = []
                for field, value in defaults.items():
                    if getattr(rule, field) != value:
                        setattr(rule, field, value)
                        updated.append(field)
                if updated:
                    rule.save(update_fields=updated)

            seen_component_ids = []
            for sequence, component_def in enumerate(rule_def.get("components", []), start=1):
                component = components.get(component_def["code"])
                if not component:
                    # Skip silently if the component definition is missing
                    continue
                rule_component, created_rc = ServiceRuleComponent.objects.update_or_create(
                    service_rule=rule,
                    service_component=component,
                    defaults={
                        "sequence": sequence,
                        "leg_owner": component_def.get("leg_owner", "COMPANY"),
                        "is_mandatory": component_def.get("is_mandatory", True),
                        "notes": component_def.get("notes"),
                    },
                )
                if not created_rc:
                    # Ensure sequence is accurate even if nothing else changed
                    if rule_component.sequence != sequence:
                        rule_component.sequence = sequence
                        rule_component.save(update_fields=["sequence"])
                seen_component_ids.append(component.id)

            ServiceRuleComponent.objects.filter(service_rule=rule).exclude(
                service_component_id__in=seen_component_ids
            ).delete()

    def _ensure_png_import_local_rates(self, origin, destination, components):
        supplier = self._ensure_self_supplier()
        rate_card, _ = PartnerRateCard.objects.get_or_create(
            name="Self PNG Import Local Charges",
            defaults={
                "supplier": supplier,
                "currency_code": "PGK",
                "valid_from": timezone.now().date(),
            },
        )
        updates = []
        if rate_card.supplier != supplier:
            rate_card.supplier = supplier
            updates.append("supplier")
        if rate_card.currency_code != "PGK":
            rate_card.currency_code = "PGK"
            updates.append("currency_code")
        if updates:
            rate_card.save(update_fields=updates)

        lane, _ = PartnerRateLane.objects.get_or_create(
            rate_card=rate_card,
            origin_airport=origin,
            destination_airport=destination,
            shipment_type="IMPORT",
            defaults={"mode": "AIR"},
        )
        if lane.mode != "AIR":
            lane.mode = "AIR"
            lane.save(update_fields=["mode"])

        self._ensure_partner_rates_for_lane(lane, components, PNG_LOCAL_IMPORT_RATE_DEFS)
        return lane

    def _ensure_png_export_local_rates(self, origin, destination, components):
        supplier = self._ensure_self_supplier()
        rate_card, _ = PartnerRateCard.objects.get_or_create(
            name="Self PNG Export Local Charges",
            defaults={
                "supplier": supplier,
                "currency_code": "PGK",
                "valid_from": timezone.now().date(),
            },
        )
        updates = []
        if rate_card.supplier != supplier:
            rate_card.supplier = supplier
            updates.append("supplier")
        if rate_card.currency_code != "PGK":
            rate_card.currency_code = "PGK"
            updates.append("currency_code")
        if updates:
            rate_card.save(update_fields=updates)

        lane, _ = PartnerRateLane.objects.get_or_create(
            rate_card=rate_card,
            origin_airport=origin,
            destination_airport=destination,
            shipment_type="EXPORT",
            defaults={"mode": "AIR"},
        )
        if lane.mode != "AIR":
            lane.mode = "AIR"
            lane.save(update_fields=["mode"])

        self._ensure_partner_rates_for_lane(lane, components, PNG_LOCAL_EXPORT_RATE_DEFS)
        return lane

    def _ensure_partner_rates_for_lane(self, lane, components, definitions):
        for config in definitions:
            component = components.get(config["component_code"])
            if not component:
                continue
            defaults = {
                "unit": config["unit"],
                "min_charge_fcy": config.get("min_charge_pgk"),
            }
            if config["unit"] == "KG":
                defaults["rate_per_kg_fcy"] = config.get("rate_per_kg_pgk")
                defaults["rate_per_shipment_fcy"] = None
            else:
                defaults["rate_per_shipment_fcy"] = config.get("rate_per_shipment_pgk")
                defaults["rate_per_kg_fcy"] = None

            PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=component,
                defaults=defaults,
            )

    def _ensure_partner_rates(self, supplier, lanes, components):
        rate_card, _ = PartnerRateCard.objects.get_or_create(
            name="Seed AUD Import BNE→POM",
            defaults={
                "supplier": supplier,
                "currency_code": "AUD",
                "valid_from": timezone.now().date(),
            },
        )

        created_lanes = []
        for origin, destination in lanes:
            lane, _ = PartnerRateLane.objects.get_or_create(
                rate_card=rate_card,
                origin_airport=origin,
                destination_airport=destination,
                defaults={"mode": "AIR", "shipment_type": "IMPORT"},
            )
            needs_update = []
            if lane.mode != "AIR":
                lane.mode = "AIR"
                needs_update.append("mode")
            if lane.shipment_type != "IMPORT":
                lane.shipment_type = "IMPORT"
                needs_update.append("shipment_type")
            if needs_update:
                lane.save(update_fields=needs_update)

            for config in PARTNER_RATE_DEFS:
                component = components.get(config["component_code"])
                if not component:
                    continue
                defaults = {
                    "unit": config["unit"],
                    "min_charge_fcy": config.get("min_charge_fcy"),
                }
                if config["unit"] == "KG":
                    defaults["rate_per_kg_fcy"] = config["rate_per_kg_fcy"]
                    defaults["rate_per_shipment_fcy"] = None
                else:
                    defaults["rate_per_shipment_fcy"] = config["rate_per_shipment_fcy"]
                    defaults["rate_per_kg_fcy"] = None

                PartnerRate.objects.get_or_create(
                    lane=lane,
                    service_component=component,
                    defaults=defaults,
                )
            created_lanes.append(lane)

        return created_lanes
