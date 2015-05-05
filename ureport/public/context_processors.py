from dash.orgs.models import Org
from django.conf import settings
from ureport.assets.models import Image


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

def linked_sites(request):
    all_orgs = Org.objects.filter(is_active=True).order_by('name')

    linked_sites = list(getattr(settings, 'PREVIOUS_ORG_SITES', []))

    # populate a ureport site for each org so we can link off to them
    for org in all_orgs:
        host = settings.SITE_HOST_PATTERN % org.subdomain
        org.host = host
        if org.get_config('is_on_landing_page'):
            flag = Image.objects.filter(org=org, is_active=True, image_type='F').first()
            if flag:
                linked_sites.append(dict(name=org.name, host=host, flag=flag.image.url, is_static=False))

        linked_sites_sorted = sorted(linked_sites, key=lambda k: k['name'])

    return dict(linked_orgs=linked_sites_sorted)