
import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule

def run():
    print("--- Checking Service Rule Linkage ---")
    try:
        rule = ServiceRule.objects.get(description='Prepaid D2A Export (FCA Standard)')
        print(f"Rule: {rule}")
        comps = [c.code for c in rule.components.all()]
        print(f"Components ({len(comps)}): {comps}")
        
        if 'AGENCY_EXP' in comps:
            print("✓ AGENCY_EXP is linked.")
        else:
            print("❌ AGENCY_EXP is NOT linked!")
            
    except ServiceRule.DoesNotExist:
        print("❌ Rule not found!")
        
if __name__ == "__main__":
    run()
