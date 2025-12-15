"""Reset Export COGS to allow re-seeding with carrier=PX"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from pricing_v4.models import ExportCOGS, Agent

# Delete existing ExportCOGS (they have agent=PX-CARGO which needs to change to carrier=PX)
deleted = ExportCOGS.objects.all().delete()
print(f"Deleted ExportCOGS: {deleted}")

# Delete PX-CARGO agent (no longer needed)
try:
    Agent.objects.filter(code='PX-CARGO').delete()
    print("Deleted PX-CARGO agent")
except Exception as e:
    print(f"Could not delete PX-CARGO: {e}")

print("Ready for re-seeding")
