
def set_has_better_domain(request):
    org = request.org

    # our defaults, prevent indexing and hide login link
    has_better_domain = True
    login_hidden = True

    # lookup if we are using the subdomain
    using_subdomain = request.META.get('HTTP_HOST', '').find('ureport.in') >= 0

    if org:
        # when using subdomain we can allow login link
        if using_subdomain:
            login_hidden = False

        # no custom domain allow indexing
        if not org.domain:
            has_better_domain = False

    return dict(has_better_domain=has_better_domain, login_hidden=login_hidden)


def set_is_iorg(request):
    """
    Context Processor that populates the 'is_internet_org' context variable with whether
    this request is coming in through a Facebook Internet.org proxy
    """
    is_iorg = False
    if request.META.get('HTTP_VIA', '').find('Internet.org') >= 0:
        is_iorg = True

    return dict(is_iorg=is_iorg)
