# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
# --- ADD THIS IMPORT ---
from .views import QuoteV3ViewSet, QuoteComputeV3APIView
# --- END ADD ---

app_name = 'quotes'

# --- V3 Router ---
router_v3 = DefaultRouter()
router_v3.register(r'quotes', QuoteV3ViewSet, basename='quote-v3')


urlpatterns = [
    # --- ADD THIS NEW PATH ---
    path('v3/quotes/compute/', QuoteComputeV3APIView.as_view(), name='quote-compute-v3'),
    # --- END ADD ---
    
    # This registers:
    # /api/v3/quotes/ (GET, list)
    # /api/v3/quotes/{id}/ (GET, retrieve)
    path('v3/', include(router_v3.urls)),
]