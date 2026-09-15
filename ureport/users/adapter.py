from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # accounts are created by staff or through org invitations, never by self-service signup
        return False

    def is_safe_url(self, url: str) -> bool:
        """
        Each org site is served from its own subdomain of HOSTNAME so redirects between those hosts are allowed, but
        nowhere else, regardless of how permissive ALLOWED_HOSTS is. Django does the parsing as browsers are lenient
        about slashes and backslashes in ways that are easy to get wrong.
        """
        url = (url or "").strip()
        host = urlparse(url).netloc

        allowed_hosts = {host} if host and is_site_host(host) else set()

        return url_has_allowed_host_and_scheme(url, allowed_hosts=allowed_hosts)


class MFAAdapter(DefaultMFAAdapter):
    def _get_site_name(self) -> str:
        # the org site the user is on rather than the django.contrib.sites record
        return self.request.get_host()


def is_site_host(host: str) -> bool:
    """
    Whether the given host is HOSTNAME or a subdomain of it
    """
    site_host = settings.HOSTNAME.lower()
    host = host.lower()
    return host == site_host or host.endswith("." + site_host)
