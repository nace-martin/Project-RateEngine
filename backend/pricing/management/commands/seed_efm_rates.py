# backend/pricing/management/commands/seed_efm_rates.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from decimal import Decimal

from core.models import Providers, Services
from pricing.models import Audience, Ratecards, ServiceItems

# Helper function to create or update a service
def ensure_service(code, name, basis):
    svc, created = Services.objects.get_or_create(code=code, defaults={"name": name, "basis": basis})
    if created:
        print(f"Created new service: {code}")
    return svc

# Helper function to add a service item to a rate card
def add_service_item(rc, service_code, currency, amount, *, min_amount=None, max_amount=None, tax_pct=0, percent_of_service_code=None, item_code=None):
    svc = Services.objects.get(code=service_code)
    defaults = {"currency": currency, "amount": amount, "tax_pct": tax_pct, "conditions_json": {}, "item_code": item_code}
    if min_amount is not None: defaults["min_amount"] = min_amount
    if max_amount is not None: defaults["max_amount"] = max_amount
    if percent_of_service_code is not None: defaults["percent_of_service_code"] = percent_of_service_code
    
    item, created = ServiceItems.objects.update_or_create(
        ratecard_id=rc.id, service_id=svc.id, defaults=defaults
    )
    if created:
        print(f"Added service item '{service_code}' to rate card '{rc.name}'")
    else:
        print(f"Updated service item '{service_code}' in rate card '{rc.name}'")
    return item

class Command(BaseCommand):
    help = "Seeds the database with the official EFM PNG Air Freight Rates for 2025."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Seeding EFM 2025 Rates..."))

        # --- 1. Define all necessary services from the rate card ---
        self.stdout.write("Ensuring all services exist...")
        ensure_service("CUSTOMS_CLEARANCE", "Customs Clearance", "PER_SHIPMENT")
        ensure_service("AGENCY_FEE", "Agency Fee", "PER_SHIPMENT")
        ensure_service("CUSTOMS_ENTRY_PAGE", "Customs Entry (per page)", "PER_PAGE")
        ensure_service("DOCUMENTATION_FEE", "Documentation Fee", "PER_SHIPMENT")
        ensure_service("HANDLING_GENERAL", "Handling Fee - General Cargo", "PER_SHIPMENT")
        ensure_service("TERMINAL_FEE_INT", "International Terminal Fee", "PER_SHIPMENT")
        ensure_service("CARTAGE_DELIVERY", "Cartage & Delivery", "PER_KG")
        ensure_service("FUEL_SURCHARGE_CARTAGE", "Fuel Surcharge on Cartage", "PERCENT_OF")
        ensure_service("DISBURSEMENT_FEE", "Disbursement Fee", "PERCENT_OF")

        # --- 2. Get your company's provider record ---
        # Assuming your company is "Maersk Air Freight" in the seed data.
        # If you have a different provider name, change it here.
        our_company, _ = Providers.objects.get_or_create(name="Express Freight Management", defaults={"provider_type": "AGENT"})




        # --- 3. Get or Create the Import SELL Rate Cards ---
        self.stdout.write("Creating/Updating the EFM Import SELL Menus...")
        ratecard_specs = [
            {"name": "EFM PGK Import SELL Menu 2025 (Prepaid)", "audience": "PNG_CUSTOMER_PREPAID"},
            {"name": "EFM PGK Import SELL Menu 2025 (Collect)", "audience": "OVERSEAS_AGENT_COLLECT"},
        ]


        ratecards = []
        for spec in ratecard_specs:
            audience_code = spec["audience"]
            audience_obj = Audience.get_or_create_from_code(audience_code)
            defaults = dict(
                currency="PGK",
                audience=audience_obj,
                source="CATALOG",
                status="PUBLISHED",
                effective_date="2025-01-01",
                expiry_date="2025-12-31",
                meta={},
                created_at=now(),
                updated_at=now(),
            )
            rc, created = Ratecards.objects.update_or_create(
                provider=our_company,
                name=spec["name"],
                role="SELL",
                scope="INTERNATIONAL",
                direction="IMPORT",
                defaults=defaults,
            )
            updated_fields = []
            if rc.audience_id != audience_obj.id:
                rc.audience = audience_obj
                updated_fields.append("audience")
            if updated_fields:
                rc.updated_at = now()
                updated_fields.append("updated_at")
                rc.save(update_fields=updated_fields)
            ratecards.append(rc)

        # --- 4. Add the Service Items from your Rate Cards ---
        self.stdout.write("Adding/Updating service items for the Import menus...")

        # Based on "Customs Clearance and Delivery Charges"
        for import_rc in ratecards:
            add_service_item(import_rc, "CUSTOMS_CLEARANCE", "PGK", "300.00", item_code="040-61130")
            add_service_item(import_rc, "AGENCY_FEE", "PGK", "250.00", item_code="040-61000")
            add_service_item(import_rc, "CUSTOMS_ENTRY_PAGE", "PGK", "55.00", item_code="040-61131")
            add_service_item(import_rc, "DOCUMENTATION_FEE", "PGK", "165.00", item_code="040-61160")
            add_service_item(import_rc, "HANDLING_GENERAL", "PGK", "165.00", item_code="040-61170")
            add_service_item(import_rc, "TERMINAL_FEE_INT", "PGK", "165.00", item_code="040-61030")
            add_service_item(import_rc, "CARTAGE_DELIVERY", "PGK", "1.50", min_amount="95.00", max_amount="500.00", item_code="040-61333")
            add_service_item(import_rc, "FUEL_SURCHARGE_CARTAGE", "PGK", "0.10", percent_of_service_code="CARTAGE_DELIVERY", item_code="040-61361")
            add_service_item(import_rc, "DISBURSEMENT_FEE", "PGK", "0.05", min_amount="50.00", max_amount="2500.00", item_code="040-61234", percent_of_service_code="TBA_IMPORT_TAX")  # Note: You'll need a way to calculate the import tax for this to work automatically

        self.stdout.write(self.style.SUCCESS("Successfully seeded EFM 2025 Import rates."))


