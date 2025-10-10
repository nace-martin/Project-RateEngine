from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RatecardFileViewSet

router = DefaultRouter()
router.register(r'ratecard-files', RatecardFileViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
