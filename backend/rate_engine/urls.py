from core.views import healthz
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def root_redirect(_request):
    return redirect(getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000"))


urlpatterns = [
    path('', root_redirect),
    path('healthz', healthz, name='healthz'),
    path('healthz/', healthz, name='healthz_slash'),
    path('admin/', admin.site.urls),

    # Include app URLs
    path('api/', include('quotes.urls')),
    path('api/', include('parties.urls')),
    path('api/', include('core.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/v3/', include('services.urls')),
    path('api/v4/', include('pricing_v4.urls')),
]

if settings.ENABLE_BROWSABLE_API:
    urlpatterns += [
        path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    if settings.SERVE_STATIC_FILES:
        urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
