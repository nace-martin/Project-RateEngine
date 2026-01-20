"""Add PICKUP to Export D2A service rules that have PICKUP_FUEL_ORG"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceRuleComponent, ServiceComponent

pickup = ServiceComponent.objects.get(code='PICKUP')
rules = ServiceRule.objects.filter(mode='AIR', direction='EXPORT', service_scope='D2A')

print(f'Found {rules.count()} Export D2A rules')

added = 0
for rule in rules:
    if not ServiceRuleComponent.objects.filter(service_rule=rule, service_component=pickup).exists():
        ServiceRuleComponent.objects.create(
            service_rule=rule, 
            service_component=pickup, 
            sequence=50
        )
        added += 1
        print(f'  Added PICKUP to: {rule}')

print(f'Total added: {added}')
