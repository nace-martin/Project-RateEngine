from django.urls import path

from .views import FxRefreshView

urlpatterns = [
    path('refresh', FxRefreshView.as_view(), name='fx-refresh'),
]
