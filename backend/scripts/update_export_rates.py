"""
Update Export rate cards with correct BUY and SELL rates.

BUY rates (our costs):
- Freight: 6.30-16.30/kg depending on destination
- Terminal: K35 for AWB/BIC/BSC, K0.17/kg for MXC, K0.15/kg for BPC

SELL rates (customer charges):
- Terminal: K50 for AWB/DOC/Terminal, K0.20/kg + K45 for Security, K0.20/kg min K50 for Build-Up
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent
from core.models import Airport

pom = Airport.objects.get(iata_code='POM')

# =============================================================================
# STEP 1: Update BUY rates with correct freight values
# =============================================================================
print('=== Updating BUY Rates ===')

buy_card = PartnerRateCard.objects.get(name='PX Export Buy Rates 2024')
print(f'BUY Card: {buy_card.name}')

# Correct BUY freight rates per destination
BUY_FREIGHT = {
    'BNE': {'min': 160, 'normal': 6.30, '100kg': 5.90, '200kg': 5.70, '500kg': 5.40},
    'CNS': {'min': 160, 'normal': 5.00, '100kg': 4.90, '200kg': 4.70, '500kg': 4.70},
    'SYD': {'min': 160, 'normal': 8.00, '100kg': 7.50, '200kg': 7.10, '500kg': 6.80},
    'HKG': {'min': 160, 'normal': 20.50, '100kg': 15.40, '200kg': 15.40, '500kg': 15.40},
    'MNL': {'min': 160, 'normal': 10.40, '100kg': 8.00, '200kg': 8.00, '500kg': 8.00},
    'HIR': {'min': 160, 'normal': 6.35, '100kg': 4.80, '200kg': 4.80, '500kg': 4.80},
    'SIN': {'min': 160, 'normal': 14.10, '100kg': 10.60, '200kg': 10.60, '500kg': 10.60},
    'VLI': {'min': 160, 'normal': 14.00, '100kg': 9.60, '200kg': 8.70, '500kg': 8.70},
    'NAN': {'min': 160, 'normal': 16.30, '100kg': 12.20, '200kg': 12.20, '500kg': 12.20},
}

frt = ServiceComponent.objects.filter(code='FRT_AIR').first()

for dest_code, rates in BUY_FREIGHT.items():
    dest = Airport.objects.filter(iata_code=dest_code).first()
    if not dest:
        continue
    
    lane = PartnerRateLane.objects.filter(
        rate_card=buy_card,
        origin_airport=pom,
        destination_airport=dest
    ).first()
    
    if not lane:
        continue
    
    if frt:
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=frt,
            defaults={
                'unit': 'KG',
                'rate_per_kg_fcy': Decimal(str(rates['normal'])),
                'min_charge_fcy': Decimal(str(rates['min'])),
            }
        )
        print(f'  Updated FRT_AIR for POM->{dest_code}: {rates["normal"]}/kg')

# Update BUY terminal rates (K35 for AWB/BIC/BSC)
BUY_TERMINAL = {
    'AWB_FEE': Decimal('35.00'),
    'DOC_EXP': Decimal('35.00'),  # BIC
    'TERM_EXP': Decimal('35.00'),  # BSC - if exists
    'HND_EXP_BSC': Decimal('35.00'),  # BSC
}

for lane in buy_card.lanes.all():
    for code, rate in BUY_TERMINAL.items():
        comp = ServiceComponent.objects.filter(code=code).first()
        if comp:
            PartnerRate.objects.update_or_create(
                lane=lane, service_component=comp,
                defaults={'unit': 'SHIPMENT', 'rate_per_shipment_fcy': rate}
            )
    
    # Security MXC: K0.17/kg
    sec = ServiceComponent.objects.filter(code='SEC_EXP_MXC').first()
    if sec:
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=sec,
            defaults={'unit': 'KG', 'rate_per_kg_fcy': Decimal('0.17')}
        )
    
    # Build-Up BPC: K0.15/kg
    bpc = ServiceComponent.objects.filter(code='HND_EXP_BPC').first()
    if bpc:
        PartnerRate.objects.update_or_create(
            lane=lane, service_component=bpc,
            defaults={'unit': 'KG', 'rate_per_kg_fcy': Decimal('0.15')}
        )

print('  BUY terminal rates updated')

# =============================================================================
# STEP 2: Update SELL rates with terminal services
# =============================================================================
print()
print('=== Updating SELL Rates ===')

sell_card = PartnerRateCard.objects.filter(name__icontains='Export Sell').first()
if not sell_card:
    sell_card = PartnerRateCard.objects.filter(rate_type='SELL_RATE').first()

print(f'SELL Card: {sell_card.name if sell_card else "NOT FOUND"}')

if sell_card:
    SELL_TERMINAL = {
        'DOC_EXP': {'per_ship': Decimal('50.00')},  # Documentation Fee
        'AWB_FEE': {'per_ship': Decimal('50.00')},  # Air Waybill Fee
        'SEC_EXP_MXC': {'per_kg': Decimal('0.20'), 'per_ship': Decimal('45.00'), 'min': Decimal('45.00')},  # Security
        'HND_EXP_BSC': {'per_ship': Decimal('50.00')},  # Terminal Fee
        'HND_EXP_BPC': {'per_kg': Decimal('0.20'), 'min': Decimal('50.00')},  # Build-Up Fee
        'VALUABLE_HANDLING': {'per_ship': Decimal('100.00')},  # Valuable Cargo Handling
        'DG_ACCEPTANCE': {'per_ship': Decimal('250.00')},  # Dangerous Goods
        'LIVESTOCK_DOC': {'per_ship': Decimal('100.00')},  # Livestock Processing
    }
    
    for lane in sell_card.lanes.filter(direction='EXPORT'):
        for code, rates in SELL_TERMINAL.items():
            comp = ServiceComponent.objects.filter(code=code).first()
            if not comp:
                continue
            
            defaults = {'unit': 'SHIPMENT' if rates.get('per_ship') else 'KG'}
            if rates.get('per_ship'):
                defaults['rate_per_shipment_fcy'] = rates['per_ship']
            if rates.get('per_kg'):
                defaults['rate_per_kg_fcy'] = rates['per_kg']
            if rates.get('min'):
                defaults['min_charge_fcy'] = rates['min']
            
            PartnerRate.objects.update_or_create(
                lane=lane, service_component=comp,
                defaults=defaults
            )
    
    print('  SELL terminal rates updated')

print()
print('=== DONE ===')
print(f'BUY rates: {PartnerRate.objects.filter(lane__rate_card=buy_card).count()}')
if sell_card:
    print(f'SELL rates: {PartnerRate.objects.filter(lane__rate_card=sell_card).count()}')
