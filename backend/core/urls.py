# backend/core/urls.py

from django.urls import path
from .views import (
    HealthCheckAPIView,
    LocationV3SearchView,
    AirportSearchAPIView,
    CountryListAPIView,
    CityListAPIView,
)
from .fx_views import ManualFxUpdateView, FxStatusView

app_name = 'core'

urlpatterns = [
    path('health/', HealthCheckAPIView.as_view(), name='health-check'),
    # --- V3 ENDPOINT ---
    path('v3/locations/search/', LocationV3SearchView.as_view(), name='location-search-v3'),
    path('v3/core/airports/search/', AirportSearchAPIView.as_view(), name='airport-search'),
    path('v3/core/countries/', CountryListAPIView.as_view(), name='country-list'),
    path('v3/core/cities/', CityListAPIView.as_view(), name='city-list'),
    
    # --- V4 FX ENDPOINTS ---
    path('v4/fx/manual-update/', ManualFxUpdateView.as_view(), name='fx-manual-update'),
    path('v4/fx/status/', FxStatusView.as_view(), name='fx-status'),
]

