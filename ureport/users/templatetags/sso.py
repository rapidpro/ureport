from urllib.parse import urlparse

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag(takes_context=True)
def sso_login_url(context, provider, process="login"):
    """
    The URL to start a single sign-on login (or connection, for an already logged in user) with the given provider.
    Identity providers need one registered callback URL, so the flow is always started on the root host and the user
    is sent back to the host they came from.
    """
    request = context["request"]
    protocol = settings.ACCOUNT_DEFAULT_HTTP_PROTOCOL

    next_url = context.get("redirect_field_value") or settings.LOGIN_REDIRECT_URL
    if not urlparse(next_url).netloc:
        next_url = f"{protocol}://{request.get_host()}{next_url}"

    login_url = provider.get_login_url(request, process=process, next=next_url)

    return f"{protocol}://{settings.HOSTNAME}{login_url}"
