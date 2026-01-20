"""
Script to add fuel surcharge components to service rules.
Run with: python manage.py shell < scripts/add_fuel_to_rules.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceRuleComponent, ServiceComponent
from ratecards.models import PartnerRate, PartnerRateLane

# Get the new fuel surcharge components
fuel_org = ServiceComponent.objects.get(code='PICKUP_FUEL_ORG')
fuel_dst = ServiceComponent.objects.get(code='PICKUP_FUEL_DST')

print(f"PICKUP_FUEL_ORG linked to: {fuel_org.percent_of_component}")
print(f"PICKUP_FUEL_DST linked to: {fuel_dst.percent_of_component}")

# 1. Add to service rules
print("\n--- Adding to Service Rules ---")
rules = ServiceRule.objects.filter(is_active=True, mode='AIR')
added = 0

for rule in rules:
    for fuel in [fuel_org, fuel_dst]:
        # Check if component's leg matches what rule uses
        if not ServiceRuleComponent.objects.filter(
            service_rule=rule, 
            service_component=fuel
        ).exists():
            ServiceRuleComponent.objects.create(
                service_rule=rule, 
                service_component=fuel, 
                sequence=100  # After base components
            )
            added += 1
            print(f"  Added {fuel.code} to {rule}")

print(f"\nAdded {added} fuel surcharge component links to service rules")

# 2. Add rates to existing lanes (copy from old PICKUP_FUEL if exists)
print("\n--- Adding Rates to Lanes ---")
old_fuel = ServiceComponent.objects.filter(code='PICKUP_FUEL').first()

if old_fuel:
    # Get all existing rates for old PICKUP_FUEL
    old_rates = PartnerRate.objects.filter(service_component=old_fuel)
    print(f"Found {old_rates.count()} existing PICKUP_FUEL rates to migrate")
    
    for rate in old_rates:
        # Create rate for PICKUP_FUEL_ORG (same lane)
        if not PartnerRate.objects.filter(lane=rate.lane, service_component=fuel_org).exists():
            PartnerRate.objects.create(
                lane=rate.lane,
                service_component=fuel_org,
                unit=rate.unit,
                rate_per_kg_fcy=rate.rate_per_kg_fcy,
                rate_per_shipment_fcy=rate.rate_per_shipment_fcy,  # This is the percentage
                min_charge_fcy=rate.min_charge_fcy,
                max_charge_fcy=rate.max_charge_fcy,
            )
            print(f"  Created PICKUP_FUEL_ORG rate on lane {rate.lane.id}")
else:
    print("No old PICKUP_FUEL component found, skipping rate migration")

# 3. Verify
print("\n--- Verification ---")
print(f"PICKUP_FUEL_ORG rates: {PartnerRate.objects.filter(service_component=fuel_org).count()}")
print(f"PICKUP_FUEL_DST rates: {PartnerRate.objects.filter(service_component=fuel_dst).count()}")

# 4. Remove old PICKUP_FUEL from service rules
print("\n--- Cleaning Up Old PICKUP_FUEL ---")
if old_fuel:
    removed = ServiceRuleComponent.objects.filter(service_component=old_fuel).delete()
    print(f"Removed {removed[0]} old PICKUP_FUEL rule links")

print("\nDone!")
