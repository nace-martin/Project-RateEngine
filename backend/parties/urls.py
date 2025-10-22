# backend/parties/urls.py

from django.urls import path
from .views import CompanySearchAPIView, CompanyContactListAPIView # Add CompanyContactListAPIView

app_name = 'parties'

urlpatterns = [
    path('v2/parties/search/', CompanySearchAPIView.as_view(), name='company-search-v2'),
    # --- ADD THIS LINE ---
    path('v2/parties/companies/<uuid:company_id>/contacts/', CompanyContactListAPIView.as_view(), name='company-contacts-v2'),
]