
def set_assets_processor(request):
    """
    Simple context processor that overwrite the assets of 'org' on the context if org
    is present in the request.
    """
    if getattr(request, 'org', None):
        org = request.org
        pattern_bg = org.images.filter(is_active=True, image_type='P')
        pattern_bg = pattern_bg.order_by('-pk').first()
        banner_bg = org.images.filter(is_active=True, image_type='B')
        banner_bg = banner_bg.order_by('-pk').first()

        return dict(pattern_bg=pattern_bg, banner_bg=banner_bg)
    else:
        return dict()
