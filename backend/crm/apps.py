from django.apps import AppConfig


class CrmConfig(AppConfig):
    """Migration-only compatibility stub.

    Retained solely because quotes.0036_quote_opportunity depends on crm.0001_initial.
    No business models, routes, views, serializers, or runtime logic exist in this app.
    """

    default_auto_field = "django.db.models.AutoField"
    name = "crm"
