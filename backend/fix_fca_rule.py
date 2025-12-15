"""
Fix Export D2A FCA Service Rule to match rate card components.

The problem: Export D2A FCA rule uses components (SEC_EXP_MXC, DOC_EXP_AWB, etc)
that don't match the seeded rate card components (PICKUP_SELL, DOC_EXP_SELL, etc).

This script syncs the FCA rule with the EXW rule which has matching rates.
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceRuleComponent, ServiceComponent

def fix_fca_rule():
    # Get the FCA rule
    fca_rule = ServiceRule.objects.filter(
        direction='EXPORT', 
        service_scope='D2A', 
        incoterm='FCA'
    ).first()
    
    if not fca_rule:
        print("FCA rule not found!")
        return
    
    # Get the EXW rule which has matching rate card components
    exw_rule = ServiceRule.objects.filter(
        direction='EXPORT', 
        service_scope='D2A', 
        incoterm='EXW'
    ).first()
    
    if not exw_rule:
        print("EXW rule not found!")
        return
    
    # Get component codes from EXW rule
    exw_comps = list(ServiceRuleComponent.objects.filter(
        service_rule=exw_rule
    ).values_list('service_component__code', flat=True))
    
    print(f"EXW rule components: {exw_comps}")
    
    # Get current FCA components
    fca_comps = list(ServiceRuleComponent.objects.filter(
        service_rule=fca_rule
    ).values_list('service_component__code', flat=True))
    
    print(f"FCA rule components (before): {fca_comps}")
    
    # Clear FCA rule components
    deleted, _ = ServiceRuleComponent.objects.filter(service_rule=fca_rule).delete()
    print(f"Deleted {deleted} old FCA components")
    
    # Add components from EXW rule
    for code in exw_comps:
        comp = ServiceComponent.objects.get(code=code)
        ServiceRuleComponent.objects.create(
            service_rule=fca_rule, 
            service_component=comp
        )
    
    # Verify
    new_fca_comps = list(ServiceRuleComponent.objects.filter(
        service_rule=fca_rule
    ).values_list('service_component__code', flat=True))
    
    print(f"FCA rule components (after): {new_fca_comps}")
    print("Done!")

if __name__ == "__main__":
    fix_fca_rule()
