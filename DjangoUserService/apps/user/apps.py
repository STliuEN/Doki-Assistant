from django.apps import AppConfig


class UserConfig(AppConfig):
    """User application configuration.

    Schema changes and development data are explicit management commands. The
    web process must never create databases, run migrations, or seed accounts
    as a side effect of importing the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.user"
