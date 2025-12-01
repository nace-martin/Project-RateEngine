import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from pricing_v3.models import RateCard, RateLine, LocalFeeRule
from services.models import ServiceComponent

def check_data():
    print("--- Checking Rate Cards ---")
    cards = RateCard.objects.filter(name__icontains="EFM")
    if not cards.exists():
        print("No EFM Rate Card found!")
    else:
        for card in cards:
            print(f"Found Card: {card.name} (ID: {card.id})")
            print(f"   Origin: {card.origin_zone}, Dest: {card.destination_zone}")
            print("   Lines:")
            for line in card.lines.all():
                print(f"     - {line.component.code}: {line.method} (Min: {line.min_charge})")
                for brk in line.breaks.all():
                    print(f"       > {brk.from_value} - {brk.to_value}: {brk.rate}")

    print("\n--- Checking Local Fees (POM) ---")
    # Assuming POM is a location, let's look for fees linked to POM or PGK currency
    fees = LocalFeeRule.objects.filter(currency="PGK")
    if not fees.exists():
        print("No PGK Local Fees found!")
    else:
        for fee in fees:
            print(f"Found Fee: {fee.component.code} ({fee.method})")
            print(f"   Rate: {fee.rate_per_unit or fee.flat_amount}")

if __name__ == "__main__":
    check_data()
