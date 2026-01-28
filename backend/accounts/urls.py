from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .user_management import UserViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('', include(router.urls)),
]
