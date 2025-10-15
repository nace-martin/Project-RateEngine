# backend/quotes/urls.py

from django.urls import path
from .views_v2 import CreateQuoteAPIViewV2 #, QuotePDFView # Add QuotePDFView

app_name = 'quotes'

urlpatterns = [
    path('v2/quotes/compute/', CreateQuoteAPIViewV2.as_view(), name='create-quote-v2'),
    # --- ADD THIS NEW URL PATTERN ---
    # path('v2/quotes/<uuid:quote_id>/pdf/', QuotePDFView.as_view(), name='get-quote-pdf'),
]