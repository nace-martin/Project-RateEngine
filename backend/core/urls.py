# backend/core/urls.py

from django.urls import path
from .views import LocationSearchAPIView

app_name = 'core'

urlpatterns = [
    path('v2/locations/search/', LocationSearchAPIView.as_view(), name='location-search-v2'),
]
