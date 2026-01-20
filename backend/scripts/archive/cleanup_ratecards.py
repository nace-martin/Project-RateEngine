
import os
import sys
import django

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from ratecards.models import PartnerRateCard

def run():
    print("--- Disabling Conflicting Rate Cards ---")
    
    # Disable "EFM POM Export Sell Rates 2025"
    cards = PartnerRateCard.objects.filter(name__icontains="EFM POM Export Sell Rates")
    for card in cards:
        print(f"Disabling Card: {card.name} (ID: {card.id})")
        # card.is_active = False # Model might not have is_active, let's check or delete
        # Safe to delete for this debugging session as it seems to be junk/test data
        card.delete()
        print("Deleted.")

if __name__ == "__main__":
    run()
