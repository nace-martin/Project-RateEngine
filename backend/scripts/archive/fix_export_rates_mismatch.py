"""
Fix Export D2A rate mismatch.

The service rule uses FRT_AIR_EXP, AWB_FEE_SELL, etc.
But the BUY rate card has FRT_AIR, AWB_FEE, etc.

Solution: Add rates for the actual components referenced in service rules.
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent, ServiceRule

buy_card = PartnerRateCard.objects.get(name='PX Export Buy Rates 2024')
print(f'Card: {buy_card.name}')

# For each Export D2A rule component, ensure BUY rate exists
# Using the SAME rates as existing components (treating _EXP as same as base)
COMPONENT_RATES = {
    'FRT_AIR_EXP': {'rate_per_kg_fcy': None, 'copy_from': 'FRT_AIR'},
    'AWB_FEE_SELL': {'rate_per_shipment_fcy': Decimal('35.00')},
    'DOC_EXP_SELL': {'rate_per_shipment_fcy': Decimal('35.00')},
    'AGENCY_EXP_SELL': {'rate_per_shipment_fcy': Decimal('35.00')},  # Agency fee
    'CLEARANCE_SELL': {'rate_per_shipment_fcy': Decimal('100.00')},  # Clearance
    'CUSTOMS_ENTRY': {'rate_per_shipment_fcy': Decimal('55.00')},   # Customs entry
}

for lane in buy_card.lanes.filter(direction='EXPORT'):
    dest = lane.destination_airport.iata_code
    
    for code, config in COMPONENT_RATES.items():
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            print(f'  {code}: Component not found')
            continue
        
        if config.get('copy_from'):
            # Copy rate from another component
            source_comp = ServiceComponent.objects.filter(code=config['copy_from']).first()
            source_rate = PartnerRate.objects.filter(lane=lane, service_component=source_comp).first()
            if source_rate:
                PartnerRate.objects.update_or_create(
                    lane=lane,
                    service_component=comp,
                    defaults={
                        'unit': source_rate.unit,
                        'rate_per_kg_fcy': source_rate.rate_per_kg_fcy,
                        'rate_per_shipment_fcy': source_rate.rate_per_shipment_fcy,
                        'min_charge_fcy': source_rate.min_charge_fcy,
                        'max_charge_fcy': source_rate.max_charge_fcy,
                    }
                )
        else:
            # Direct rate
            PartnerRate.objects.update_or_create(
                lane=lane,
                service_component=comp,
                defaults={
                    'unit': 'SHIPMENT',
                    'rate_per_shipment_fcy': config.get('rate_per_shipment_fcy'),
                }
            )
    
    print(f'  {dest}: rates added')

print(f'Total BUY rates: {PartnerRate.objects.filter(lane__rate_card=buy_card).count()}')
