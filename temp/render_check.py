import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
import django
django.setup()
from django.template.loader import render_to_string
from types import SimpleNamespace

quote = SimpleNamespace(
    quote_number="QT-36",
    created_at=None,
    valid_until=None,
    status="FINALIZED",
    shipment_type="EXPORT",
    payment_term="PREPAID",
    incoterm="DAP",
    mode="AIR",
)
context = {"quote": quote}
rendered = render_to_string("quotes/quote_pdf.html", context)
for needle in ["{{ quote.valid_until", "{{ quote.shipment_type", "{{ quote.payment_term", "{{ quote.status"]:
    print(needle, needle in rendered)
