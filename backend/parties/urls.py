# backend/parties/urls.py

from django.urls import path
from .views import CompanySearchAPIView, CompanyContactListAPIView, ContactListAPIView, CustomerListView, CustomerDetailView # Add CompanyContactListAPIView

app_name = 'parties'

urlpatterns = [
    path('v2/customers/', CustomerListView.as_view(), name='customer-list-v2'),
    path('v2/customers/<uuid:pk>/', CustomerDetailView.as_view(), name='customer-detail-v2'),
    path('v2/parties/search/', CompanySearchAPIView.as_view(), name='company-search-v2'),
    # --- ADD THIS LINE ---
    path('v2/parties/companies/<uuid:company_id>/contacts/', CompanyContactListAPIView.as_view(), name='company-contacts-v2'),
    path('contacts/', ContactListAPIView.as_view(), name='contact-list'),
]
