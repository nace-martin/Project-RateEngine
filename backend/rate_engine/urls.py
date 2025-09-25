from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from quotes.views import QuotationViewSet, QuoteVersionCreateView, QuoteVersionLockView

router = DefaultRouter()
router.register(r'quotations', QuotationViewSet, basename='quotations')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/quotes/<int:id>/versions', QuoteVersionCreateView.as_view(), name='quote-version-create'),
    path('api/quote-versions/<int:id>/lock', QuoteVersionLockView.as_view(), name='quote-version-lock'),
]
