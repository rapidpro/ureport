"""
This module offers one templatetag called ``load_dashblocks``.

``load_dashblocks`` does a query for all active DashBlock objects
for the passed in DashBlockType and Org on request. (identified by the slug)  You can
then access that list within your context.

It accepts 2 parameter:
    
    org
        The Org set on the request to filter DashBlocks for that org.

    slug
        The slug/key of the DashBlockType to load DashBlocks for.

        If you want to pass it by name, you have to use quotes on it.
        Otherwise just use the variable name.

Syntax::

    {% load_dashblocks [org] [name] %}

Example usage::

    {% load dashblocks %}

    ...

    {% load_dashblocks request.org "home_banner_blocks" %}

    ...

    Note: You may also use the shortcut tag 'load_qbs' eg: {% load_qbs request.org "home_banner_blocks %}

.. note::

    If you specify a slug that has no associated dash block, then an error message
    will be inserted in your template.  You may change this text by setting
    the value of the DASHBLOCK_STRING_IF_INVALID setting.

"""
from django import template
from django.conf import settings
from django.db import models

register = template.Library()

DashBlockType = models.get_model('dashblocks', 'dashblocktype')
DashBlock = models.get_model('dashblocks', 'dashblock')

@register.simple_tag(takes_context=True)
def load_dashblocks(context, org, slug, tag=None):
    if not org:
        return ''
    
    try:
        dashblock_type = DashBlockType.objects.get(slug=slug)
    except DashBlockType.DoesNotExist:
        return getattr(settings, 'DASHBLOCK_STRING_IF_INVALID', '<b><font color="red">DashBlockType with slug: %s not found</font></b>') % slug

    dashblocks = DashBlock.objects.filter(dashblock_type=dashblock_type, org=org, is_active=True).order_by('-priority')

    # filter by our tag if one was specified
    if not tag is None:
        dashblocks = dashblocks.filter(tags__icontains=tag)

    
    context[slug] = dashblocks

    return ''

@register.simple_tag(takes_context=True)
def load_qbs(context, org, slug, tag=None):
    return load_dashblocks(context, org, slug, tag)
