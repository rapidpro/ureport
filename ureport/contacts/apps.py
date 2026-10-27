from django.apps import AppConfig


class ContactsConfig(AppConfig):
    name = "ureport.contacts"
    verbose_name = "Contacts"

    def ready(self):
        from . import signals  # noqa: F401
