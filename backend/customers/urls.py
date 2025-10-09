from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, AddressViewSet

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'addresses', AddressViewSet)

urlpatterns = [
    path('', include(router.urls)),
]