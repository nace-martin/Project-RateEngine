from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PricingEngineView, CustomerDiscountViewSet, ProductCodeListViewSet,
    CustomerDiscountBulkUpsertAPIView,
    QuoteCounterpartyHintsAPIView,
    AgentViewSet, CarrierViewSet,
    ExportCOGSViewSet, ExportSellRateViewSet,
    ImportCOGSViewSet, ImportSellRateViewSet,
    DomesticCOGSViewSet, DomesticSellRateViewSet,
    LocalSellRateViewSet, LocalCOGSRateViewSet,
    LogicalRateCardsView, V4RateCardUploadView
)


# Create router for viewsets
router = DefaultRouter()
router.register(r'discounts', CustomerDiscountViewSet, basename='customer-discounts')
router.register(r'product-codes', ProductCodeListViewSet, basename='product-codes')
router.register(r'agents', AgentViewSet, basename='agents')
router.register(r'carriers', CarrierViewSet, basename='carriers')

# V4 Sell Rate endpoints
router.register(r'rates/export', ExportSellRateViewSet, basename='export-sell-rates')
router.register(r'rates/export-cogs', ExportCOGSViewSet, basename='export-cogs-rates')
router.register(r'rates/import', ImportSellRateViewSet, basename='import-sell-rates')
router.register(r'rates/import-cogs', ImportCOGSViewSet, basename='import-cogs-rates')
router.register(r'rates/domestic', DomesticSellRateViewSet, basename='domestic-sell-rates')
router.register(r'rates/domestic-cogs', DomesticCOGSViewSet, basename='domestic-cogs-rates')
router.register(r'rates/local-sell', LocalSellRateViewSet, basename='local-sell-rates')
router.register(r'rates/local-cogs', LocalCOGSRateViewSet, basename='local-cogs-rates')


urlpatterns = [
    path('quote/calculate/', PricingEngineView.as_view(), name='pricing-v4-calculate'),
    path('quote/counterparty-hints/', QuoteCounterpartyHintsAPIView.as_view(), name='pricing-v4-counterparty-hints'),
    path('discounts/bulk-upsert/', CustomerDiscountBulkUpsertAPIView.as_view(), name='customer-discounts-bulk-upsert'),
    path('rates/upload/', V4RateCardUploadView.as_view(), name='pricing-v4-rates-upload'),
    path('rate-cards/', LogicalRateCardsView.as_view(), name='logical-rate-cards'),
    path('', include(router.urls)),
]


