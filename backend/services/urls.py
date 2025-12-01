from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceComponentViewSet

router = DefaultRouter()
router.register(r'services', ServiceComponentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
