from django import template

register = template.Library()


@register.simple_tag
def account_status(user):
    """
    Whether the user has verified their current email address and set up two-factor authentication
    """
    return {
        "verified": user.emailaddress_set.filter(email=user.email, verified=True).exists(),
        "mfa": user.authenticator_set.exists(),
    }
