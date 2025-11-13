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
from services.models import ServiceComponent, IncotermRule
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate


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


class Command(BaseCommand):
    help = "Seed a minimal but complete dataset so the V3 quote compute flow can run end-to-end."

    def handle(self, *args, **options):
        with transaction.atomic():
            currencies = self._ensure_currencies()
            countries, cities, airports = self._ensure_locations()
            customer, contact, supplier = self._ensure_parties(countries["PG"], currencies["PGK"])
            policy = self._ensure_policy()
            snapshot = self._ensure_fx_snapshot()
            components = self._ensure_service_components()
            self._ensure_incoterm_rule(components)
            lane = self._ensure_partner_rates(
                supplier=supplier,
                origin=airports["BNE"],
                destination=airports["POM"],
                components=components,
            )

        self.stdout.write(self.style.SUCCESS("V3 compute seed complete"))
        self.stdout.write(f"  - Customer: {customer.name} (contact: {contact.email})")
        self.stdout.write(f"  - Supplier: {supplier.name}")
        self.stdout.write(f"  - Policy: {policy.name}")
        self.stdout.write(f"  - FX Snapshot: {snapshot.as_of_timestamp.isoformat()}")
        self.stdout.write(f"  - Partner lane: {lane.origin_airport_id} -> {lane.destination_airport_id}")

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
            defaults={"company_type": "CUSTOMER"},
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
            defaults={"company_type": "SUPPLIER"},
        )

        return customer, contact, supplier

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
        components = {}
        for definition in SERVICE_COMPONENT_DEFS:
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

    def _ensure_incoterm_rule(self, components):
        rule, _ = IncotermRule.objects.get_or_create(
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="EXW",
            defaults={"description": "Seed AIR IMPORT EXW rule"},
        )
        rule.service_components.set(components.values())
        return rule

    def _ensure_partner_rates(self, supplier, origin, destination, components):
        rate_card, _ = PartnerRateCard.objects.get_or_create(
            name="Seed AUD Import BNE→POM",
            defaults={
                "supplier": supplier,
                "currency_code": "AUD",
                "valid_from": timezone.now().date(),
            },
        )

        lane, _ = PartnerRateLane.objects.get_or_create(
            rate_card=rate_card,
            origin_airport=origin,
            destination_airport=destination,
            defaults={"mode": "AIR", "shipment_type": "IMPORT"},
        )

        for config in PARTNER_RATE_DEFS:
            component = components[config["component_code"]]
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

        return lane
