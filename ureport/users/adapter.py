import logging
from urllib.parse import urlencode, urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)


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

    def get_sso_only_message(self, email: str):
        """
        Returns the error for an email address whose domain requires single sign-on, or None
        """
        domain = email.rsplit("@", 1)[-1].lower() if email else ""
        return {d.lower(): m for d, m in settings.SSO_ONLY_DOMAINS.items()}.get(domain)

    def pre_login(self, request, user, *, email_verification, signal_kwargs, email, signup, redirect_url):
        # users whose email domain requires single sign-on can't log in any other way
        is_sso = bool(signal_kwargs and signal_kwargs.get("sociallogin"))
        sso_only_message = self.get_sso_only_message(user.email)
        if not is_sso and sso_only_message:
            messages.error(request, sso_only_message)
            login_url = reverse("account_login")
            if redirect_url:
                login_url += "?" + urlencode({"next": redirect_url})
            return redirect(login_url)

        return super().pre_login(
            request,
            user,
            email_verification=email_verification,
            signal_kwargs=signal_kwargs,
            email=email,
            signup=signup,
            redirect_url=redirect_url,
        )


def is_site_host(host: str) -> bool:
    """
    Whether the given host is HOSTNAME or a subdomain of it
    """
    site_host = settings.HOSTNAME.lower()
    host = host.lower()
    return host == site_host or host.endswith("." + site_host)


def user_display(user) -> str:
    # users are identified by email everywhere, so that's what allauth's pages and messages should show
    return user.email or str(user)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Single sign-on only ever logs in an existing account, matched by an email address that the provider has verified
    and that the provider is trusted for (its EMAIL_AUTHENTICATION setting). A login with an unknown email ends on the
    signup closed page rather than creating an account.

    Providers that don't say whether an email is verified, or only identify users by a principal name (e.g. Entra ID's
    upn or preferred_username, which it only puts in the ID token), are trusted for the domains in their verified_email
    setting, so that a deployment can trust a tenant for the domains it owns and nothing else.
    """

    def is_open_for_signup(self, request, sociallogin):
        # a social login that gets here didn't match an existing user, so log what the provider claimed
        extra = sociallogin.account.extra_data or {}
        logger.warning(
            "social login fell through to closed signup: provider=%s email=%r upn=%r preferred_username=%r",
            sociallogin.account.provider,
            get_claim(extra, "email"),
            get_claim(extra, "upn"),
            get_claim(extra, "preferred_username"),
        )
        return False

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        # allauth renders a generic error page without logging why, so record the cause
        extra_context = extra_context or {}
        logger.warning(
            "social login failed: provider=%s error=%s exception=%r state_found=%s idp_error=%r idp_error_description=%r",
            getattr(provider, "id", provider),
            error,
            exception,
            extra_context.get("state") is not None,
            request.GET.get("error"),
            request.GET.get("error_description"),
        )

        super().on_authentication_error(request, provider, error, exception, extra_context)

    def authenticate_by_email(self, sociallogin):
        self._add_claimed_email(sociallogin)

        match = super().authenticate_by_email(sociallogin)
        if not match:
            return None

        user, email = match
        if not user.is_active:
            return None

        # a trusted provider vouching for the address is as good as the user confirming it from an email, so they
        # don't need to have done that first and can keep their password rather than having it wiped as a precaution
        user.emailaddress_set.exclude(email=email).update(primary=False)
        EmailAddress.objects.update_or_create(user=user, email=email, defaults={"verified": True, "primary": True})

        return match

    def _add_claimed_email(self, sociallogin):
        """
        Providers that don't report email addresses may still identify the user by one in another claim, which is
        verified only if the provider is trusted for its domain.
        """
        if sociallogin.email_addresses:
            return

        email = get_email(sociallogin.account.extra_data)
        if email:
            verified = self.is_email_verified(sociallogin.provider, email)
            sociallogin.email_addresses = [EmailAddress(email=email, verified=verified, primary=True)]


def get_email(extra_data: dict):
    """
    The email a provider's claims identify the user by: an email claim, or else a principal name that is one
    """
    for name in ("email", "upn", "preferred_username"):
        value = get_claim(extra_data, name)
        if value and "@" in value:
            return value.strip().lower()

    return None


def get_claim(extra_data: dict, name: str):
    """
    Looks up a claim in a provider's extra data. OpenID Connect data is nested by source, with the ID token carrying
    claims the userinfo endpoint may not.
    """
    for source in ((extra_data or {}).get("userinfo"), (extra_data or {}).get("id_token"), extra_data):
        if isinstance(source, dict) and source.get(name):
            return str(source[name])

    return None
