# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django import template
from django.conf import settings
from django.template import TemplateSyntaxError
from django.utils.safestring import mark_safe

from ureport.utils import get_linked_orgs

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def question_results(question):
    if not question:
        return None

    try:
        results = question.get_results()
        if results:
            return results[0]
    except Exception:
        if getattr(settings, "PROD", False):
            logger.error(
                "Question get results without segment in template tag raised exception", extra={"stack": True}
            )
        return None


@register.filter
def question_segmented_results(question, field):
    if not question:
        return None

    segment = None
    if field == "age":
        segment = dict(age="Age")
    elif field == "gender":
        segment = dict(gender="Gender")

    try:
        results = question.get_results(segment=segment)
        if results:
            return results
    except Exception:
        if getattr(settings, "PROD", False):
            logger.error("Question get results with segment in template tag raised exception", extra={"stack": True})
        return None


@register.filter
def get_range(value):
    return range(value)


@register.filter
def config(org, name):
    if not org:
        return None

    return org.get_config(name)


@register.filter
def org_arrow_link(org):
    if not org:
        return None

    if org.language in getattr(settings, "RTL_LANGUAGES", []):
        return mark_safe("&#8592;")

    return mark_safe("&#8594;")


@register.filter
def org_color(org, index):
    if not org:
        return None

    org_colors = org.get_config("common.colors")

    if org_colors:
        org_colors = org_colors.split(",")
    else:
        if org.get_config("common.primary_color") and org.get_config("common.secondary_color"):
            org_colors = [
                org.get_config("common.primary_color").strip(),
                org.get_config("common.secondary_color").strip(),
            ]
        else:
            org_colors = [
                getattr(settings, "UREPORT_DEFAULT_PRIMARY_COLOR"),
                getattr(settings, "UREPORT_DEFAULT_SECONDARY_COLOR"),
            ]

    return org_colors[int(index) % len(org_colors)].strip()


@register.filter
def transparency(color, alpha):
    if not color:
        return color

    if color[0] == "#":
        color = color[1:]

    if len(color) != 6:
        raise TemplateSyntaxError("add_transparency expect a long hexadecimal color, got: [%s]" % color)

    rgb_color = [int(c) for c in bytearray.fromhex(color)]
    rgb_color.append(alpha)

    return "rgba(%s, %s, %s, %s)" % tuple(rgb_color)


def lessblock(parser, token):
    args = token.split_contents()
    if len(args) != 1:
        raise TemplateSyntaxError("lessblock tag takes no arguments, got: [%s]" % ",".join(args))

    nodelist = parser.parse(("endlessblock",))
    parser.delete_first_token()
    return LessBlockNode(nodelist)


class LessBlockNode(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        output = self.nodelist.render(context)
        style_output = '<style type="text/less" media="all">%s</style>' % output
        return style_output


# register our tag
lessblock = register.tag(lessblock)


@register.inclusion_tag("public/org_flags.html", takes_context=True)
def show_org_flags(context):
    request = context["request"]
    linked_orgs = get_linked_orgs(request.user.is_authenticated)
    return dict(
        linked_orgs=linked_orgs,
        break_pos=min(len(linked_orgs) / 2, 9),
        STATIC_URL=settings.STATIC_URL,
        is_iorg=context["is_iorg"],
    )


@register.simple_tag(takes_context=True)
def org_host_link(context):
    request = context["request"]
    try:
        org = request.org
        return org.build_host_link(True)
    except Exception:
        return "https://%s" % getattr(settings, "HOSTNAME", "localhost")


@register.filter
def check_policy(org, policy_type):
    if not org:
        return None

    from ureport.policies.models import Policy

    return Policy.objects.filter(
        policy_type=policy_type,
        language=org.language,
        is_active=True).order_by("-created_on").count()
