# backend/parties/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'parties'

# --- V3 Router ---
router_v3 = DefaultRouter()
router_v3.register(r'customers', views.CustomerV3ViewSet, basename='customer-v3')

urlpatterns = [
    # --- V3 ENDPOINTS ---
    path('v3/', include(router_v3.urls)),
    path('v3/branding/organization/', views.OrganizationBrandingSettingsView.as_view(), name='organization-branding-settings-v3'),
    path('v3/parties/search/', views.CompanyV3SearchView.as_view(), name='company-search-v3'),
    path('v3/parties/companies/search/', views.CompanyV3SearchView.as_view(), name='company-search-v3-alias'),
    path('v3/parties/companies/<uuid:company_id>/contacts/', views.CompanyContactListV3View.as_view(), name='company-contacts-v3'),
]
