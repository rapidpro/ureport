import operator
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


def set_config_display_flags(request):
    org = request.org
    context = dict()
    if org:
        backend_options = org.backends.filter(is_active=True).values_list('slug', flat=True)

        context['district_zoom'] = reduce(operator.or_, [bool(org.get_config('%s.district_label' % option)) for option in backend_options], False)
        context['ward_zoom'] = reduce(operator.or_, [bool(org.get_config('%s.ward_label' % option)) for option in backend_options], False)
        context['show_maps'] = reduce(operator.or_, [bool(org.get_config('%s.state_label' % option)) for option in backend_options], False)
        context['show_age_stats'] = reduce(operator.or_, [bool(org.get_config('%s.age_label' % option)) for option in backend_options], False)
        context['show_gender_stats'] = reduce(operator.or_, [bool(org.get_config('%s.gender_label' % option)) for option in backend_options], False)
        context['show_occupation_stats'] = reduce(operator.or_, [bool(org.get_config('%s.occupation_label' % option)) for option in backend_options], False)

    return context


def set_org_lang_params(request):
    """
    Context Processor that populates the 'is_rtl_org' context variable with whether
    the org language is a right to left language
    """
    is_rtl_org = False
    org_lang = 'en_US'
    org = request.org
    if org and org.language in getattr(settings, 'RTL_LANGUAGES', []):
        is_rtl_org = True

        org_langs = getattr(settings, 'ORG_LANG_MAP', {})
        org_lang = org_langs.get(org.language)

    return dict(is_rtl_org=is_rtl_org, org_lang=org_lang)


def set_story_widget_url(request):
    """
    Context Processor that populates the 'story_widget_url' context variable with whether
    the story widget URL
    """
    story_widget_url = getattr(settings, 'STORY_WIDGET_URL', None)
    story_widget_url = "%s/" % story_widget_url if story_widget_url and not story_widget_url.endswith('/') else story_widget_url
    return dict(story_widget_url=story_widget_url)
