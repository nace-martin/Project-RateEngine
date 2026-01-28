
import os
import sys
import django

sys.path.append(os.path.join(os.getcwd(), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from services.models import ServiceRule, ServiceComponent

def inspect_rules():
    with open('service_rules_dump.txt', 'w') as f:
        f.write("--- Inspecting Export Service Rules ---\n")
        rules = ServiceRule.objects.filter(direction='EXPORT')
        
        for rule in rules:
            f.write(f"\nRule ID: {rule.pk} | Mode: {rule.mode} | Scope: {rule.service_scope} | Incoterm: {rule.incoterm}\n")
            components = rule.service_components.filter(is_active=True)
            for comp in components:
                f.write(f"  - {comp.code}: {comp.description}\n")
                
        f.write("\n--- Inspecting Pickup Components ---\n")
        pickups = ServiceComponent.objects.filter(description__icontains='pick')
        for p in pickups:
            f.write(f"Component: {p.code} - {p.description}\n")
            
        f.write("\n--- Inspecting Fuel Surcharge Components ---\n")
        fscs = ServiceComponent.objects.filter(description__icontains='fuel')
        for p in fscs:
            f.write(f"Component: {p.code} - {p.description}\n")

if __name__ == "__main__":
    inspect_rules()
