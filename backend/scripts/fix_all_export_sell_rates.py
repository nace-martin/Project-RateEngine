"""
Comprehensive fix for Export SELL rates.

From user's rate sheet:
Additional Export Fees:
- Documentation Fee: K50.00/AWB
- Air Waybill Fee: K50.00/AWB
- Security Surcharge Fee: K0.20/kg + K45 flat, min K45
- Terminal Fee: K50.00/AWB
- Build-Up Fee: K0.20/kg, min K50.00

Clearance and Cartage Charges:
- Customs Clearance: K300.00/AWB
- Agency Fee: K250.00/AWB
- Pick up Fee: K1.50/kg, min K95, max K500
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent

# Get SELL rate card
sell_card = PartnerRateCard.objects.filter(rate_type='SELL_RATE', name__icontains='Export').first()
if not sell_card:
    sell_card = PartnerRateCard.objects.filter(rate_type='SELL_RATE').first()

print(f'SELL Card: {sell_card.name}')

# Define ALL correct SELL rates
SELL_RATES = {
    # Documentation
    'DOC_EXP_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('50.00'),
        'rate_per_kg_fcy': None,
        'min_charge_fcy': None,
        'max_charge_fcy': None,
    },
    'AWB_FEE_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('50.00'),
        'rate_per_kg_fcy': None,
        'min_charge_fcy': None,
        'max_charge_fcy': None,
    },
    
    # Terminal & Handling - using existing component codes
    'HND_EXP_BSC': {  # Terminal Fee
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('50.00'),
        'rate_per_kg_fcy': None,
        'min_charge_fcy': None,
        'max_charge_fcy': None,
    },
    'HND_EXP_BPC': {  # Build-Up Fee
        'unit': 'KG',
        'rate_per_shipment_fcy': None,
        'rate_per_kg_fcy': Decimal('0.20'),
        'min_charge_fcy': Decimal('50.00'),
        'max_charge_fcy': None,
    },
    'SEC_EXP_MXC': {  # Security Surcharge Fee (K0.20/kg + K45 flat)
        'unit': 'KG',
        'rate_per_shipment_fcy': Decimal('45.00'),  # Flat fee
        'rate_per_kg_fcy': Decimal('0.20'),         # Per kg
        'min_charge_fcy': Decimal('45.00'),
        'max_charge_fcy': None,
    },
    
    # Customs & Brokerage
    'CLEARANCE_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('300.00'),
        'rate_per_kg_fcy': None,
        'min_charge_fcy': None,
        'max_charge_fcy': None,
    },
    'AGENCY_EXP_SELL': {
        'unit': 'SHIPMENT',
        'rate_per_shipment_fcy': Decimal('250.00'),
        'rate_per_kg_fcy': None,
        'min_charge_fcy': None,
        'max_charge_fcy': None,
    },
    
    # Collection
    'PICKUP': {
        'unit': 'KG',
        'rate_per_shipment_fcy': None,
        'rate_per_kg_fcy': Decimal('1.50'),
        'min_charge_fcy': Decimal('95.00'),
        'max_charge_fcy': Decimal('500.00'),
    },
}

print()
print('=== Updating SELL rates ===')
for lane in sell_card.lanes.filter(direction='EXPORT'):
    print(f'Lane: {lane.origin_airport.iata_code} -> {lane.destination_airport.iata_code}')
    
    for code, config in SELL_RATES.items():
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            print(f'  {code}: Component not found')
            continue
        
        rate, created = PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=comp,
            defaults=config
        )
        print(f'  {code}: {"created" if created else "updated"} - {config.get("rate_per_shipment_fcy") or config.get("rate_per_kg_fcy")}/{"SHIP" if config.get("rate_per_shipment_fcy") else "KG"}')

# Ensure Terminal, BuildUp, Security are in the D2A Export service rules
print()
print('=== Adding missing components to D2A Export rules ===')
d2a_rules = ServiceRule.objects.filter(service_scope='D2A', direction='EXPORT')

COMPONENTS_TO_ADD = ['HND_EXP_BSC', 'HND_EXP_BPC', 'SEC_EXP_MXC']

for rule in d2a_rules:
    print(f'Rule: {rule}')
    for code in COMPONENTS_TO_ADD:
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            continue
        
        src, created = ServiceRuleComponent.objects.get_or_create(
            service_rule=rule,
            service_component=comp,
            defaults={'sequence': 100}
        )
        if created:
            print(f'  Added {code}')
        else:
            print(f'  {code} already exists')

print()
print('=== Done ===')
