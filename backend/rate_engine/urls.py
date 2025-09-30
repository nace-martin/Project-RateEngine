from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from quotes.views import QuotationViewSet, QuoteVersionCreateView, QuoteVersionLockView
from customers.views import CustomerViewSet
from core.views import StationViewSet

router = DefaultRouter()
router.register(r'quotations', QuotationViewSet, basename='quotations')
router.register(r'customers', CustomerViewSet, basename='customers')
router.register(r'stations', StationViewSet, basename='stations')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/auth/', include('accounts.urls')),
    path('api/quotes/<int:id>/versions', QuoteVersionCreateView.as_view(), name='quote-version-create'),
    path('api/quote-versions/<int:id>/lock', QuoteVersionLockView.as_view(), name='quote-version-lock'),
]
