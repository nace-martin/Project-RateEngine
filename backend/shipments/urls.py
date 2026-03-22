from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ShipmentAddressBookViewSet,
    ShipmentSettingsAPIView,
    ShipmentTemplateViewSet,
    ShipmentViewSet,
)

app_name = "shipments"

router = DefaultRouter()
router.register(r"shipments", ShipmentViewSet, basename="shipment")
router.register(r"shipments/address-book", ShipmentAddressBookViewSet, basename="shipment-address-book")
router.register(r"shipments/templates", ShipmentTemplateViewSet, basename="shipment-template")

urlpatterns = [
    path("v3/", include(router.urls)),
    path("v3/shipments/settings/", ShipmentSettingsAPIView.as_view(), name="shipment-settings"),
]
