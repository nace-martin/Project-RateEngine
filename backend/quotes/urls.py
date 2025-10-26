# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuoteViewSet
from .views_v2 import CreateQuoteAPIViewV2, GetQuoteAPIViewV2
from .views_v3 import QuoteComputeV3APIView, QuoteRetrieveV3APIView

app_name = 'quotes'

router = DefaultRouter()
router.register(r'quotes', QuoteViewSet, basename='quote')

urlpatterns = [
    # --- V3 ENDPOINTS ---
    path('v3/quotes/compute/', QuoteComputeV3APIView.as_view(), name='quote-compute-v3'),
    path('v3/quotes/<uuid:id>/', QuoteRetrieveV3APIView.as_view(), name='quote-retrieve-v3'),

    # --- V2 ENDPOINTS (keep them) ---
    path('v2/', include(router.urls)),
    path('v2/quotes/compute/', CreateQuoteAPIViewV2.as_view(), name='create-quote-v2'),
    path('v2/quotes/<uuid:quote_id>/', GetQuoteAPIViewV2.as_view(), name='get-quote-v2'),
]
