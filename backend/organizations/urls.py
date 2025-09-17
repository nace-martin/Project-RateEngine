from django.urls import path

from .views import OrganizationsListView

urlpatterns = [
    path('', OrganizationsListView.as_view(), name='organizations-list'),
]
