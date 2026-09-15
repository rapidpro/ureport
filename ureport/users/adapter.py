from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

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


def is_site_host(host: str) -> bool:
    """
    Whether the given host is HOSTNAME or a subdomain of it
    """
    site_host = settings.HOSTNAME.lower()
    host = host.lower()
    return host == site_host or host.endswith("." + site_host)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Single sign-on only ever logs in an existing account, matched by an email address the provider has verified and
    which we have verified for that account too. A login with an unknown email ends on the signup closed page rather
    than creating an account.

    Some providers identify users by a claim other than a verified email, e.g. the principal name from Entra ID.
    Because such claims are only as trustworthy as the tenant issuing them, a provider app can opt in with
    `identity_claim` (the claim name) and `identity_claim_domains` (the email domains it may vouch for) in its
    settings.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def authenticate_by_email(self, sociallogin):
        self._add_identity_claim(sociallogin)

        match = super().authenticate_by_email(sociallogin)
        if not match:
            return None

        user, email = match

        # only accept a match backed by a verified address on our side: matching on the user's email field alone
        # would have allauth wipe their password as a precaution, and an inactive account shouldn't be connected
        if not user.is_active or not EmailAddress.objects.filter(user=user, email=email, verified=True).exists():
            return None

        return match

    def _add_identity_claim(self, sociallogin):
        """
        Adds the provider's configured identity claim as a verified email address if it's in a trusted domain
        """
        if any(a.verified for a in sociallogin.email_addresses):
            return

        app = sociallogin.provider.app if sociallogin.provider else None
        app_settings = app.settings if app else {}
        claim = app_settings.get("identity_claim")
        domains = {d.lower() for d in app_settings.get("identity_claim_domains", [])}
        if not claim or not domains:
            return

        value = get_claim(sociallogin.account.extra_data, claim)
        if not value or "@" not in value:
            return

        value = value.strip().lower()
        if value.rpartition("@")[2] not in domains:
            return

        sociallogin.email_addresses.append(
            EmailAddress(email=value, verified=True, primary=not sociallogin.email_addresses)
        )


def get_claim(extra_data: dict, name: str):
    """
    Looks up a claim in a provider's extra data. OpenID Connect data is nested by source, with the ID token carrying
    claims the userinfo endpoint may not.
    """
    for source in (extra_data.get("userinfo"), extra_data.get("id_token"), extra_data):
        if isinstance(source, dict) and source.get(name):
            return str(source[name])

    return None
