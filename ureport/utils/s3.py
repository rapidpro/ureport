from django.core.files.storage import DefaultStorage


class PublicFileStorage(DefaultStorage):
    default_acl = "public-read"
