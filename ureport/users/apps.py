from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "ureport.users"
    label = "ureport_users"  # "users" is taken by smartmin.users, whose models the user CRUDL still relies on
    verbose_name = "Users"

    def ready(self):
        from . import signals  # noqa: F401
