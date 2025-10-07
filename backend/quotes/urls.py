from django.urls import path
from .views import QuoteVersionCreateView, QuoteVersionLockView, QuotationViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'quotations', QuotationViewSet, basename='quotations')

from .views_v2 import ComputeV2

urlpatterns = [
    path('quotes/<int:id>/versions', QuoteVersionCreateView.as_view(), name='quote-version-create'),
    path('quote-versions/<int:id>/lock', QuoteVersionLockView.as_view(), name='quote-version-lock'),
    path('quote/compute2', ComputeV2.as_view(), name='quote-compute-v2'),
]
urlpatterns += router.urls
