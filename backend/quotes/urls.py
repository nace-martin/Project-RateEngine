from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientViewSet, RateCardViewSet, QuoteViewSet, RouteListView

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'ratecards', RateCardViewSet)
router.register(r'quotes', QuoteViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('routes/', RouteListView.as_view(), name='route-list'),
]