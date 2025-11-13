# backend/core/urls.py

from django.urls import path
from .views import LocationV3SearchView, AirportSearchAPIView

app_name = 'core'

urlpatterns = [
    # --- V3 ENDPOINT ---
    path('v3/locations/search/', LocationV3SearchView.as_view(), name='location-search-v3'),
    path('v3/core/airports/search/', AirportSearchAPIView.as_view(), name='airport-search'),
]
