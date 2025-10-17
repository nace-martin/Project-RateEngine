# backend/parties/urls.py

from django.urls import path
from .views import CompanySearchAPIView

app_name = 'parties'

urlpatterns = [
    path('v2/parties/search/', CompanySearchAPIView.as_view(), name='company-search-v2'),
]