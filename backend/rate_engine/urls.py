from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
# from quotes.views import QuotationViewSet, QuoteVersionCreateView, QuoteVersionLockView
# from core.views import StationViewSet

router = DefaultRouter()
# router.register(r'quotations', QuotationViewSet, basename='quotations')
# router.register(r'stations', StationViewSet, basename='stations')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    # path('api/', include('customers.urls')),
    path('api/', include('parties.urls')),
    path('api/', include('quotes.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/ratecards/', include('ratecards.urls')),
]
