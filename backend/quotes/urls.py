# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    QuoteV3ViewSet,
    QuoteComputeV3APIView,
    CustomerDetailAPIView,
    RatecardListAPIView,
    RatecardUploadAPIView,
    StationListAPIView,
    QuoteVersionCreateAPIView,
    SpotChargeListCreateAPIView,
    SpotChargeCalculateAPIView,
)

app_name = 'quotes'

# --- V3 Router ---
router_v3 = DefaultRouter()
router_v3.register(r'quotes', QuoteV3ViewSet, basename='quote-v3')


urlpatterns = [
    path('v3/quotes/compute/', QuoteComputeV3APIView.as_view(), name='quote-compute-v3'),
    path('v3/quotes/<uuid:quote_id>/versions/', QuoteVersionCreateAPIView.as_view(), name='quote-version-create'),
    path('v3/quotes/<uuid:quote_id>/spot-charges/', SpotChargeListCreateAPIView.as_view(), name='spot-charge-list-create'),
    path('v3/quotes/<uuid:quote_id>/spot-charges/calculate/', SpotChargeCalculateAPIView.as_view(), name='spot-charge-calculate'),
    path('v3/customers/<uuid:customer_id>/', CustomerDetailAPIView.as_view(), name='customer-detail'),
    path('v3/ratecards/', RatecardListAPIView.as_view(), name='ratecard-list'),
    path('v3/ratecards/upload/', RatecardUploadAPIView.as_view(), name='ratecard-upload'),
    path('v3/stations/', StationListAPIView.as_view(), name='station-list'),
    path('v3/', include(router_v3.urls)),
]

