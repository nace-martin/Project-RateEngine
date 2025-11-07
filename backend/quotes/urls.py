# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuoteV3ViewSet

app_name = 'quotes'

# --- V3 Router ---
router_v3 = DefaultRouter()
router_v3.register(r'quotes', QuoteV3ViewSet, basename='quote-v3')


urlpatterns = [
    # --- V3 ENDPOINTS ---
    path('v3/', include(router_v3.urls)),
]
