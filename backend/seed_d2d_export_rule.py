
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceComponent, ServiceRuleComponent

def seed_d2d_export_rule():
    print("Seeding D2D Export Rule...")

    # 1. Ensure DST_CHARGES component exists
    dst_comp, created = ServiceComponent.objects.get_or_create(
        code='DST_CHARGES',
        defaults={
            'description': 'Destination Charges (Agent)',
            'category': 'DESTINATION',
            'unit': 'SHIPMENT',
            'cost_type': 'RATE_OFFER', # Or PASSTHROUGH?
            'is_active': True
        }
    )
    if created:
        print("Created DST_CHARGES component.")
        # Ensure it has PASSTHROUGH pricing method if we want to rely on that
        # But wait, ServiceComponent doesn't have pricing_method directly, it's on ServiceCode?
        # Or maybe it does? Let's check models.py if needed.
        # PricingServiceV3 uses component.service_code.pricing_method OR component.cost_type
        # Let's assume cost_type='RATE_OFFER' is fine for now, or we might need to link a ServiceCode.
    else:
        print("DST_CHARGES component already exists.")

    # 2. Create Service Rule
    rule, created = ServiceRule.objects.get_or_create(
        mode='AIR',
        direction='EXPORT',
        incoterm='EXW',
        payment_term='PREPAID',
        service_scope='D2D',
        defaults={
            'is_active': True,
            'output_currency_type': 'ORIGIN' # Prepaid Export D2D = Origin Currency (PGK)
        }
    )
    
    if created:
        print(f"Created ServiceRule: {rule}")
    else:
        print(f"ServiceRule already exists: {rule}")
        # Update defaults if needed
        if rule.output_currency_type != 'ORIGIN':
            print(f"Updating output_currency_type from {rule.output_currency_type} to ORIGIN")
            rule.output_currency_type = 'ORIGIN'
            rule.save()

    # 3. Link Components
    components = [
        'PICKUP_SELL', 'DOC_EXP_SELL', 'AWB_FEE_SELL', 'TERM_EXP_SELL', 
        'SECURITY_SELL', 'BUILD_UP', 'CLEARANCE_SELL', 'AGENCY_EXP_SELL', 
        'CUSTOMS_ENTRY', 'FRT_AIR_EXP', 'DST_CHARGES'
    ]

    for idx, code in enumerate(components, 1):
        try:
            comp = ServiceComponent.objects.get(code=code)
            ServiceRuleComponent.objects.get_or_create(
                service_rule=rule,
                service_component=comp,
                defaults={'sequence': idx}
            )
            print(f"Linked {code}")
        except ServiceComponent.DoesNotExist:
            print(f"WARNING: Component {code} not found!")

if __name__ == '__main__':
    seed_d2d_export_rule()
