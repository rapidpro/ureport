from django.conf import settings
from django.contrib.auth.models import Group
from rest_framework import permissions

__author__ = 'kenneth'


class CanUseAPI(permissions.BasePermission):
    message = 'Please request for permission to access this resource'

    def has_permission(self, request, view):
        g = Group.objects.filter(name=getattr(settings, 'API_ACCESS_GROUP', "API Users")).first()
        return request.user.is_superuser or (g is not None and g in request.user.groups.all())