"""
Reorganize Export origin charge groupings for better UI display.

Current grouping is confusing:
- Collection Services: PICKUP only
- Other Services: Agency, AWB, Clearance, Documentation, Fuel Surcharge

Better grouping:
- Collection Services: PICKUP, PICKUP_FUEL_ORG
- Documentation: AWB_FEE_SELL, DOC_EXP_SELL
- Customs: CLEARANCE_SELL
- Agency: AGENCY_EXP_SELL
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceComponent, ServiceCode

# The UI groups by service_code.service_category
# Let's check what service category values we have
print('=== Current ServiceCode categories ===')
for sc in ServiceCode.objects.values('service_category').distinct():
    print(' ', sc['service_category'])

print()
print('=== Updating component service_code assignments ===')

# Define which ServiceCode each component should use for proper grouping
COMPONENT_UPDATES = {
    # Collection Services - pickup related
    'PICKUP': 'ORG-PKUP-STD',  # Origin Pickup - Collection
    'PICKUP_FUEL_ORG': 'ORG-PKUP-STD',  # Origin Pickup Fuel - should be with pickup
    
    # Documentation
    'AWB_FEE_SELL': 'ORG-DOC-AWB',  # AWB Fee
    'DOC_EXP_SELL': 'ORG-DOC-STD',  # Documentation
    
    # Customs
    'CLEARANCE_SELL': 'ORG-CUST-CLR',  # Customs Clearance
    
    # Agency
    'AGENCY_EXP_SELL': 'ORG-AGEN-STD',  # Agency Fee
}

# Check what ServiceCodes exist with origin categories
print()
print('=== Available Origin ServiceCodes ===')
for sc in ServiceCode.objects.filter(location_type='ORIGIN'):
    print(f'  {sc.code}: {sc.service_category}')

# Create any missing ServiceCodes for origin
REQUIRED_CODES = {
    'ORG-PKUP-STD': {'desc': 'Origin Pickup Standard', 'cat': 'COLLECTION', 'loc': 'ORIGIN'},
    'ORG-DOC-AWB': {'desc': 'Air Waybill', 'cat': 'DOCUMENTATION', 'loc': 'ORIGIN'},
    'ORG-DOC-STD': {'desc': 'Documentation', 'cat': 'DOCUMENTATION', 'loc': 'ORIGIN'},
    'ORG-CUST-CLR': {'desc': 'Customs Clearance', 'cat': 'CUSTOMS', 'loc': 'ORIGIN'},
    'ORG-AGEN-STD': {'desc': 'Agency Services', 'cat': 'AGENCY', 'loc': 'ORIGIN'},
}

print()
print('=== Creating/updating ServiceCodes ===')
for code, config in REQUIRED_CODES.items():
    sc, created = ServiceCode.objects.update_or_create(
        code=code,
        defaults={
            'description': config['desc'],
            'service_category': config['cat'],
            'location_type': config['loc'],
            'is_active': True,
        }
    )
    print(f'  {code}: {"created" if created else "updated"}')

# Update components to use correct ServiceCodes
print()
print('=== Updating Components ===')
for comp_code, sc_code in COMPONENT_UPDATES.items():
    comp = ServiceComponent.objects.filter(code=comp_code).first()
    if not comp:
        print(f'  {comp_code}: NOT FOUND')
        continue
    
    sc = ServiceCode.objects.filter(code=sc_code).first()
    if not sc:
        print(f'  {comp_code}: ServiceCode {sc_code} NOT FOUND')
        continue
    
    comp.service_code = sc
    comp.leg = 'ORIGIN'  # Ensure leg is correct too
    comp.save()
    print(f'  {comp_code}: assigned to {sc_code} ({sc.service_category})')

print()
print('=== Done ===')
