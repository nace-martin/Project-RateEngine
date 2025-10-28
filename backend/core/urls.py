# backend/core/urls.py

from django.urls import path
from .views import LocationV3SearchView

app_name = 'core'

urlpatterns = [
    # --- V3 ENDPOINT ---
    path('v3/locations/search/', LocationV3SearchView.as_view(), name='location-search-v3'),
]
