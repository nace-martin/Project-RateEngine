import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceRule

# Check rate cards
print("=== RATE CARDS ===")
cards = PartnerRateCard.objects.all()
print(f"Total: {cards.count()}")
for card in cards:
    print(f"  - {card.name}")
    lanes = card.lanes.all()
    print(f"    Lanes: {lanes.count()}")
    for lane in lanes:
        rates = lane.rates.all()
        print(f"      {lane.origin_airport} -> {lane.destination_airport}: {rates.count()} rates")

# Check service rules  
print("\n=== SERVICE RULES ===")
rules = ServiceRule.objects.filter(mode='AIR', direction='EXPORT', service_scope='D2D')
print(f"Total D2D Export Rules: {rules.count()}")
for rule in rules:
    print(f"  - {rule.incoterm}/{rule.payment_term}: {rule.rule_components.count()} components")
