
def set_is_iorg(request):
    """
    Context Processor that populates the 'is_internet_org' context variable with whether
    this request is coming in through a Facebook Internet.org proxy
    """
    is_iorg = False
    if request.META.get('HTTP_VIA', '').find('Internet.org') >= 0:
        is_iorg = True

    print "IS_IORG (%s): %s" % (request.META.get('HTTP_VIA'), is_iorg)
    return dict(is_iorg=is_iorg)