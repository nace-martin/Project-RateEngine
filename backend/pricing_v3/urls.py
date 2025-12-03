from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    QuoteComputeView, QuoteComputeV3View, RoutingValidationView,
    ZoneViewSet, RateCardViewSet, RateLineViewSet,
    QuoteSpotRateViewSet, QuoteSpotChargeViewSet
)

router = DefaultRouter()
router.register(r'zones', ZoneViewSet)
router.register(r'rate-cards', RateCardViewSet)
router.register(r'rate-lines', RateLineViewSet)
router.register(r'spot-rates', QuoteSpotRateViewSet)
router.register(r'spot-charges', QuoteSpotChargeViewSet)

urlpatterns = [
    path('quotes/<uuid:quote_id>/compute/', QuoteComputeView.as_view(), name='quote-compute'),
    path('quotes/<uuid:quote_id>/compute_v3/', QuoteComputeV3View.as_view(), name='quote-compute-v3'),
    path('routing/validate', RoutingValidationView.as_view(), name='routing-validate'),
] + router.urls
