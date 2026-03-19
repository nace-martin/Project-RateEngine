from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Include your app's URLs
    # This will now include our new 'api/v3/quotes/compute/' URL
    path('api/', include('quotes.urls')), 
    path('api/', include('ratecards.urls')),
    path('api/', include('parties.urls')),
    path('api/', include('core.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/v3/', include('services.urls')), # Expose services under v3 for consistency or just api/
    path('api/v4/', include('pricing_v4.urls')),

    
    # Include DRF's login URLs for the Browsable API
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
