from django.urls import path
from .views import QuoteVersionCreateView, QuoteVersionLockView, QuotationViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'quotations', QuotationViewSet, basename='quotations')

urlpatterns = [
    path('quotes/<int:id>/versions', QuoteVersionCreateView.as_view(), name='quote-version-create'),
    path('quote-versions/<int:id>/lock', QuoteVersionLockView.as_view(), name='quote-version-lock'),
]
urlpatterns += router.urls
