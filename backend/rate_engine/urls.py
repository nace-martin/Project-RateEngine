"""
URL configuration for rate_engine project.

The `urlpatterns` list routes URLs to views. For more information please see:
https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/quote/', include('quotes.urls')),
    path('api/quotes/', include('quotes.urls')),
    path('api/organizations/', include('organizations.urls')),
    path('api/fx/', include('core.urls')),
]
