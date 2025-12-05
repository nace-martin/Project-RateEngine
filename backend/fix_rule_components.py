import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from services.models import ServiceRule, ServiceComponent, ServiceRuleComponent

def fix_rule_components():
    print("Fixing Service Rule Components for EXW Export D2D...")
    
    # 1. Get the Rule
    rule = ServiceRule.objects.filter(
        mode='AIR',
        direction='EXPORT',
        service_scope='D2D',
        payment_term='PREPAID',
        incoterm='EXW'
    ).first()
    
    if not rule:
        print("Rule not found!")
        return

    print(f"Found Rule: {rule.id}")
    
    # 2. Define Mappings (Standard -> Seeded)
    # Based on seed_pom_export_rates.py
    mapping = {
        'PKUP_ORG': 'PICKUP_SELL',
        'CLEAR_EXP': 'CLEARANCE_SELL',
        'DOC_EXP': 'DOC_EXP_SELL',
        'AGENCY_EXP': 'AGENCY_EXP_SELL',
        'TERM_EXP': 'TERM_EXP_SELL',
        'AWB_FEE': 'AWB_FEE_SELL',
        'SECURITY': 'SECURITY_SELL',
    }
    
    # 3. Swap Components
    for rc in rule.rule_components.all():
        current_code = rc.service_component.code
        if current_code in mapping:
            target_code = mapping[current_code]
            print(f"Checking mapping: {current_code} -> {target_code}")
            
            try:
                target_comp = ServiceComponent.objects.get(code=target_code)
                print(f" - Swapping {current_code} with {target_code}")
                rc.service_component = target_comp
                rc.save()
            except ServiceComponent.DoesNotExist:
                print(f" - Target component {target_code} does not exist. Skipping.")
                
    print("Done fixing components.")

if __name__ == "__main__":
    fix_rule_components()
