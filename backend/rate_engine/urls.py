"""
URL configuration for rate_engine project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include # Make sure 'include' is imported
from rate_engine.engine import (
    QuoteComputeView,
    QuoteDetailView,
    QuoteListView,
    OrganizationsListView,
    FxRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('accounts.urls')), # Add accounts URLs
    # API endpoints
    path("api/quote/compute", QuoteComputeView.as_view(), name="compute-quote"),
    path("api/quotes/", QuoteListView.as_view(), name="quotes-list"),
    path("api/quotes/<int:quote_id>/", QuoteDetailView.as_view(), name="quotes-detail"),
    path("api/organizations/", OrganizationsListView.as_view(), name="organizations-list"),
    path("api/fx/refresh", FxRefreshView.as_view(), name="fx-refresh"),
]
