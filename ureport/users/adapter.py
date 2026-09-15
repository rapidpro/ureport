from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter

from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # accounts are created by staff or through org invitations, never by self-service signup
        return False

    def is_safe_url(self, url: str) -> bool:
        """
        Each org site is served from its own subdomain of HOSTNAME so redirects between those hosts are allowed, but
        nowhere else, regardless of how permissive ALLOWED_HOSTS is.
        """
        url = (url or "").strip()
        if not url or url.startswith("///"):
            return False

        # check the URL as given and with backslashes normalized, as browsers treat them as slashes
        for candidate in (url, url.replace("\\", "/")):
            parsed = urlparse(candidate)
            if parsed.scheme and parsed.scheme not in ("http", "https"):
                return False
            if parsed.scheme and not parsed.netloc:
                return False
            if parsed.netloc and not is_site_host(parsed.netloc):
                return False

        return True


def is_site_host(host: str) -> bool:
    """
    Whether the given host is HOSTNAME or a subdomain of it
    """
    site_host = settings.HOSTNAME.lower()
    host = host.lower()
    return host == site_host or host.endswith("." + site_host)
