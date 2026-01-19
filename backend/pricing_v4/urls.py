from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import PricingEngineView, CustomerDiscountViewSet, ProductCodeListViewSet


# Create router for viewsets
router = DefaultRouter()
router.register(r'discounts', CustomerDiscountViewSet, basename='customer-discounts')
router.register(r'product-codes', ProductCodeListViewSet, basename='product-codes')


urlpatterns = [
    path('quote/calculate/', PricingEngineView.as_view(), name='pricing-v4-calculate'),
    path('', include(router.urls)),
]
