from django.apps import AppConfig


class QuotesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quotes'

    def ready(self):
        # Import signals to register them
        import quotes.signals  # noqa: F401

