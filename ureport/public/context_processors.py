from django.conf import settings


def set_has_better_domain(request):
    """
    Context Processor that populates 'has_better_domain' and 'login_hidden'
    context variables

    * **has_better_domain** - True when request is not using the preferred domain. default: True
    * **login_hidden** - False when request is using the subdomain.hostname url. default: True

    """
    org = request.org

    # our defaults, prevent indexing and hide login link
    has_better_domain = True
    show_login = False

    hostname = getattr(settings, 'HOSTNAME', 'localhost')

    # lookup if we are using the subdomain
    using_subdomain = request.META.get('HTTP_HOST', '').find(hostname) >= 0

    if org:
        # when using subdomain we can allow login link
        if using_subdomain:
            show_login = True

        # no custom domain or not using sudomain, allow indexing
        if not org.domain or not using_subdomain:
            has_better_domain = False

    return dict(has_better_domain=has_better_domain, show_login=show_login)


def set_is_iorg(request):
    """
    Context Processor that populates the 'is_iorg' context variable with whether
    this request is coming in through a Facebook Internet.org proxy
    """
    is_iorg = False
    if request.META.get('HTTP_VIA', '').find('Internet.org') >= 0:
        is_iorg = True

    return dict(is_iorg=is_iorg)
