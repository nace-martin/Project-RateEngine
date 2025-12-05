
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import RouteLaneConstraint

def check_constraints():
    print("Checking RouteLaneConstraint Data...")
    constraints = RouteLaneConstraint.objects.all()
    for c in constraints:
        print(f"Constraint: {c.origin.code}->{c.destination.code}")
        print(f"  Service Level: {c.service_level}")
        print(f"  Aircraft: {c.aircraft_type.code if c.aircraft_type else 'None'}")
        print(f"  Priority: {c.priority}")
        print("-" * 20)

if __name__ == '__main__':
    check_constraints()
