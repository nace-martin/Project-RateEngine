# backend/pricing_v2/apps.py
from django.apps import AppConfig
class PricingV2Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing_v2"
    verbose_name = "Pricing V2"