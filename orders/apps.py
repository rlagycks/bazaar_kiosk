from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'

    def ready(self):
        # Importing registers the checks; nothing else here has side effects.
        from orders import checks  # noqa: F401
