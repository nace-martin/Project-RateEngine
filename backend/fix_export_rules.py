import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from services.models import ServiceRule

def fix_export_rules():
    print("Checking Export D2D Prepaid Rules...")
    
    # 1. Find Export D2D Prepaid Rules
    rules = ServiceRule.objects.filter(
        direction='EXPORT',
        service_scope='D2D',
        payment_term='PREPAID'
    )
    
    print(f"Found {rules.count()} rules.")
    
    target_rule = None
    
    for rule in rules:
        print(f"Rule ID: {rule.id}, Output: {rule.output_currency_type}, Active: {rule.is_active}")
        
        # We prefer the one that is already PGK or ORIGIN if it exists
        if rule.output_currency_type in ['PGK', 'ORIGIN']:
            target_rule = rule
            
    if not target_rule:
        # If none, pick the first one and update it
        target_rule = rules.first()
        
    if target_rule:
        print(f"Selected Target Rule: {target_rule.id}")
        
        # Update Target Rule
        target_rule.output_currency_type = 'PGK' # Force PGK
        target_rule.is_active = True
        target_rule.save()
        print(f"Updated Target Rule {target_rule.id} to PGK and Active.")
        
        # Deactivate others
        for rule in rules:
            if rule.id != target_rule.id:
                rule.is_active = False
                rule.save()
                print(f"Deactivated Rule {rule.id}")
                
    else:
        print("No rules found to fix!")

    # Verify
    active_rules = ServiceRule.objects.filter(
        direction='EXPORT',
        service_scope='D2D',
        payment_term='PREPAID',
        is_active=True
    )
    print(f"Active Rules after fix: {active_rules.count()}")
    for r in active_rules:
        print(f"Active Rule: {r.output_currency_type}")

if __name__ == "__main__":
    fix_export_rules()
