from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from django.conf import settings
from django.contrib.auth import get_user_model
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


def is_site_host(host: str) -> bool:
    """
    Whether the given host is HOSTNAME or a subdomain of it
    """
    site_host = settings.HOSTNAME.lower()
    host = host.lower()
    return host == site_host or host.endswith("." + site_host)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Single sign-on only ever logs in an existing account. The provider's email is matched against our users, so a
    login with an unknown email ends on the signup closed page rather than creating an account.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        extra_data = sociallogin.account.extra_data

        # providers vary in what identifies the user: an email they have verified, or for Entra ID the principal
        # name. An email claim the provider hasn't verified is not enough to log into the account with that email.
        verified = [a.email for a in sociallogin.email_addresses if a.verified]
        email = verified[0] if verified else (extra_data.get("upn") or extra_data.get("preferred_username"))
        if not email:
            return

        email = email.lower()
        if not sociallogin.email_addresses:
            sociallogin.email_addresses = [EmailAddress(email=email, verified=True, primary=True)]

        # connect a first-time social login to the account that already has that email
        if not sociallogin.is_existing:
            user = get_user_model().objects.filter(email=email, is_active=True).first()
            if user:
                sociallogin.connect(request, user)
