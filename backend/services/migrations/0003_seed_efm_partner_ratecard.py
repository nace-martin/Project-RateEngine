# backend/services/migrations/0002_seed_efm_partner_ratecard.py
import json
from django.db import migrations
from django.utils.translation import gettext_lazy as _
import datetime

# Define names/codes we will look up
SUPPLIER_NAME = "Express Freight Management"
SERVICE_NAME_FREIGHT = "Freight"
SERVICE_NAME_PICKUP = "Origin Pickup"

# New services to create
SERVICE_NAME_FUEL_PICKUP = "Fuel Surcharge (Origin Pickup)" # Renamed for clarity
SERVICE_NAME_SECURITY = "Origin Security (X-Ray)"

PORT_CODE_BNE = "BNE"
PORT_CODE_SYD = "SYD"
PORT_CODE_POM = "POM"


def seed_efm_partner_ratecard(apps, schema_editor):
    """
    Seeds the EFM AUD Partner Rate Card for BNE/SYD -> POM.
    Correctly links Fuel Surcharge to the Pickup service.
    """
    # Get models
    Company = apps.get_model("parties", "Company")
    ServiceComponent = apps.get_model("services", "ServiceComponent")
    Airport = apps.get_model("core", "Airport")
    PartnerRateCard = apps.get_model("ratecards", "PartnerRateCard")
    PartnerRateLane = apps.get_model("ratecards", "PartnerRateLane")
    PartnerRate = apps.get_model("ratecards", "PartnerRate")

    # === 1. Find or Create Supplier ===
    supplier, _ = Company.objects.get_or_create(
        name=SUPPLIER_NAME,
        defaults={'company_type': 'SUPPLIER'}
    )

    # === 2. Find or Create required ServiceComponents ===
    
    # Find existing services
    print("Looking for freight service...")
    service_freight_qs = ServiceComponent.objects.filter(description__iexact=SERVICE_NAME_FREIGHT)
    print(f"Found {service_freight_qs.count()} freight services")
    for s in service_freight_qs:
        print(s)
    
    print("Looking for pickup service...")
    service_pickup_qs = ServiceComponent.objects.filter(description__iexact=SERVICE_NAME_PICKUP)
    print(f"Found {service_pickup_qs.count()} pickup services")
    for s in service_pickup_qs:
        print(s)

    try:
        service_freight = ServiceComponent.objects.get(description__iexact=SERVICE_NAME_FREIGHT)
        service_pickup = ServiceComponent.objects.get(description__iexact=SERVICE_NAME_PICKUP)
    except ServiceComponent.DoesNotExist as e:
        raise Exception(
            f"Could not find core service. "
            "Make sure the services migration (0001_initial) "
            "has been run."
        ) from e

    # Create new Fuel Surcharge service, LINKED to the Pickup service
    if not ServiceComponent.objects.filter(description=SERVICE_NAME_FUEL_PICKUP).exists():
        service_fuel_pickup = ServiceComponent.objects.create(
            description=SERVICE_NAME_FUEL_PICKUP,
            code='FUEL_PKUP',
            category='ORIGIN',
            unit='PERCENT_OF_SERVICE', # <-- This is the key
            cost_type='COGS',
            cost_source='PARTNER_RATECARD',
            cost_currency_type='FCY',
            tax_rate=0.00
        )
    else:
        service_fuel_pickup = ServiceComponent.objects.get(description=SERVICE_NAME_FUEL_PICKUP)

    if not ServiceComponent.objects.filter(description=SERVICE_NAME_SECURITY).exists():
        service_security = ServiceComponent.objects.create(
            description=SERVICE_NAME_SECURITY,
            code='SEC_ORG',
            category='ORIGIN',
            unit='PER_KG',
            cost_type='COGS',
            cost_source='PARTNER_RATECARD',
            cost_currency_type='FCY',
            tax_rate=0.00
        )
    else:
        service_security = ServiceComponent.objects.get(description=SERVICE_NAME_SECURITY)

    # === 3. Find Airports ===
    try:
        bne_port = Airport.objects.get(iata_code=PORT_CODE_BNE)
        syd_port = Airport.objects.get(iata_code=PORT_CODE_SYD)
        pom_port = Airport.objects.get(iata_code=PORT_CODE_POM)
    except Airport.DoesNotExist as e:
        raise Exception(
            f"Could not find Airport. Please ensure core location data is seeded."
        ) from e

    # === 4. Create PartnerRateCard ===
    rate_card, created = PartnerRateCard.objects.get_or_create(
        name="EFM POM - Tier 1 BNE/SYD - POM",
        supplier=supplier,
        defaults={
            'currency_code': 'AUD',
            'valid_until': datetime.date(2025, 6, 30),
            'mode': 'AIR',
            'shipment_type': 'GENERAL'
        }
    )
    
    if not created:
        print("Rate card already exists, skipping seed.")
        return

    # === 5. Create Lanes ===
    lane_bne, _ = PartnerRateLane.objects.get_or_create(
        rate_card=rate_card,
        origin_airport=bne_port,
        destination_airport=pom_port
    )
    
    lane_syd, _ = PartnerRateLane.objects.get_or_create(
        rate_card=rate_card,
        origin_airport=syd_port,
        destination_airport=pom_port
    )

    # === 6. Create Rates ===
    
    # --- BNE -> POM Rates ---
    PartnerRate.objects.create(
        lane=lane_bne,
        service_component=service_freight,
        unit='PER_KG',
        min_charge_fcy=330.00,
        tiering_json=json.dumps([
            {'break': 45, 'rate': 7.75},
            {'break': 100, 'rate': 6.75},
            {'break': 250, 'rate': 6.55},
            {'break': 500, 'rate': 6.25},
            {'break': 1000, 'rate': 5.95}
        ])
    )
    PartnerRate.objects.create(
        lane=lane_bne,
        service_component=service_pickup,
        unit='PER_KG',
        min_charge_fcy=85.00,
        tiering_json=json.dumps([
            {'break': 0, 'rate': 0.26},
            {'break': 1000, 'rate': 0.21}
        ])
    )
    PartnerRate.objects.create(
        lane=lane_bne,
        service_component=service_fuel_pickup, # <-- Correct service
        unit='PERCENT_OF_SERVICE', # <-- Correct unit
        flat_fee_fcy=20.00 # Storing the percentage '20' here
    )
    PartnerRate.objects.create(
        lane=lane_bne,
        service_component=service_security,
        unit='PER_KG',
        min_charge_fcy=70.00,
        tiering_json=json.dumps([
            {'break': 0, 'rate': 0.36}
        ])
    )

    # --- SYD -> POM Rates ---
    PartnerRate.objects.create(
        lane=lane_syd,
        service_component=service_freight,
        unit='PER_KG',
        min_charge_fcy=400.00,
        tiering_json=json.dumps([
            {'break': 45, 'rate': 7.05},
            {'break': 100, 'rate': 7.55},
            {'break': 250, 'rate': 7.30},
            {'break': 500, 'rate': 6.95},
            {'break': 1000, 'rate': 6.70}
        ])
    )
    PartnerRate.objects.create(
        lane=lane_syd,
        service_component=service_pickup,
        unit='PER_KG',
        min_charge_fcy=85.00,
        tiering_json=json.dumps([
            {'break': 0, 'rate': 0.26},
            {'break': 1000, 'rate': 0.21}
        ])
    )
    PartnerRate.objects.create(
        lane=lane_syd,
        service_component=service_fuel_pickup, # <-- Correct service
        unit='PERCENT_OF_SERVICE', # <-- Correct unit
        flat_fee_fcy=20.00 # Storing the percentage '20' here
    )
    PartnerRate.objects.create(
        lane=lane_syd,
        service_component=service_security,
        unit='PER_KG',
        min_charge_fcy=70.00,
        tiering_json=json.dumps([
            {'break': 0, 'rate': 0.36}
        ])
    )

class Migration(migrations.Migration):

    dependencies = [
        ('services', '0002_seed_initial_services'),
        ('ratecards', '0003_alter_partnerrate_unit'),
        ('parties', '0002_company_company_type'),
        ('core', '0002_seed_initial_data'),
    ]

    operations = [
        migrations.RunPython(seed_efm_partner_ratecard, migrations.RunPython.noop),
    ]
