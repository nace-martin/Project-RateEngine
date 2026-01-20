"""Add missing rates for Export D2A components"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from decimal import Decimal
from ratecards.models import PartnerRateCard, PartnerRate
from services.models import ServiceComponent

# Get BUY rate card
buy_card = PartnerRateCard.objects.get(name='PX Export Buy Rates 2024')
print(f'Card: {buy_card.name}')

# Components that need rates
MISSING_RATES = {
    'DOC_EXP': {'rate': Decimal('35.00'), 'unit': 'SHIPMENT'},
    # Note: PICKUP_SELL and SECURITY_SELL are SELL components
    # They shouldn't be in the BUY cost calculation
}

for lane in buy_card.lanes.filter(direction='EXPORT'):
    for code, config in MISSING_RATES.items():
        comp = ServiceComponent.objects.filter(code=code).first()
        if not comp:
            print(f'  {code}: Component not found')
            continue
        
        PartnerRate.objects.update_or_create(
            lane=lane,
            service_component=comp,
            defaults={
                'unit': config['unit'],
                'rate_per_shipment_fcy': config['rate']
            }
        )
    print(f'  {lane.destination_airport.iata_code}: Added rates')

# PICKUP_SELL and SECURITY_SELL are SELL-only - remove from D2A rules
from services.models import ServiceRule, ServiceRuleComponent

d2a_rules = ServiceRule.objects.filter(service_scope='D2A')
for code in ['PICKUP_SELL', 'SECURITY_SELL']:
    comp = ServiceComponent.objects.filter(code=code).first()
    if comp:
        removed = ServiceRuleComponent.objects.filter(
            service_rule__in=d2a_rules,
            service_component=comp
        ).delete()
        print(f'Removed {code} from D2A rules: {removed}')

print('Done!')
