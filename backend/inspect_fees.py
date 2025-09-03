import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

import django
django.setup()

from rate_engine.models import Ratecards, RatecardFees

rc = Ratecards.objects.get(name="PNG Domestic BUY Rates (Flat per KG)")
print("RC", rc.id)
for rf in RatecardFees.objects.filter(ratecard=rc).select_related("fee_type"):
    ft = rf.fee_type
    print(ft.code, ft.basis, str(rf.amount), str(rf.min_amount), rf.currency)

