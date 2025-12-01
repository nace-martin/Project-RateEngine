import sys
from services.models import ServiceComponent, ServiceRule
from ratecards.models import PartnerRateCard
from quotes.models import Quote

def run():
    print("--- Cleaning Rating & Quote Data (Preserving Users/Accounts) ---")

    # 1. Delete Quotes (Transactions)
    # This automatically deletes QuoteVersions, QuoteLines, and QuoteTotals via cascade
    q_count, _ = Quote.objects.all().delete()
    print(f"Deleted {q_count} Quotes (and related versions/lines).")

    # 2. Delete Partner Rate Cards (Pricing Data)
    # This automatically deletes PartnerRateLanes and PartnerRates
    rc_count, _ = PartnerRateCard.objects.all().delete()
    print(f"Deleted {rc_count} Partner Rate Cards (and related lanes/rates).")

    # 3. Delete Service Rules (The "Recipes")
    # This automatically deletes ServiceRuleComponents
    sr_count, _ = ServiceRule.objects.all().delete()
    print(f"Deleted {sr_count} Service Rules.")

    # 4. Delete Service Components (The "Ingredients")
    # We delete these to ensure no 'bad ingredients' are left over.
    # Since Quotes and Rates are already gone, this is safe to do now.
    sc_count, _ = ServiceComponent.objects.all().delete()
    print(f"Deleted {sc_count} Service Components.")

    print("--- Cleanup Complete. Accounts, Customers, & Airports were preserved. ---")

# Allow running directly or via shell
if __name__ == '__main__':
    run()
