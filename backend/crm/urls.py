from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "crm"

router_v3 = DefaultRouter()
router_v3.register(r"opportunities", views.OpportunityViewSet, basename="opportunity")
router_v3.register(r"interactions", views.InteractionViewSet, basename="interaction")
router_v3.register(r"tasks", views.TaskViewSet, basename="task")

urlpatterns = [
    path("v3/crm/", include(router_v3.urls)),
]
