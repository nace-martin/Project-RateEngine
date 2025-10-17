# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuoteViewSet
from .views_v2 import CreateQuoteAPIViewV2 #, QuotePDFView

app_name = 'quotes'

router = DefaultRouter()
router.register(r'quotes', QuoteViewSet, basename='quote')

urlpatterns = [
    path('v2/', include(router.urls)),
    path('v2/quotes/compute/', CreateQuoteAPIViewV2.as_view(), name='create-quote-v2'),
    # path('v2/quotes/<uuid:quote_id>/pdf/', QuotePDFView.as_view(), name='get-quote-pdf'),
]