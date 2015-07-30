
def set_has_better_domain(request):
    has_better_domain = True
    if request.META.get('HTTP_HOST', '').find('ureport.in') >= 0 and not request.org.domain:
        has_better_domain = False

    login_hidden = False
    if request.org.domain:
        login_hidden = True

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
