# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django import forms, template
from django.conf import settings
from django.template import TemplateSyntaxError
from django.urls import reverse
from django.utils.safestring import mark_safe

from ureport.utils import UNICEF_REGIONS, get_linked_orgs

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter(name="add_placeholder")
def add_placeholder(field):
    field.field.widget.attrs["placeholder"] = field.label
    return field


@register.filter
def question_results(question):
    if not question:
        return None

    try:
        results = question.get_results()
        if results:
            return results[0]
    except Exception:
        if getattr(settings, "IS_PROD", False):
            logger.error(
                "Question get results without segment in template tag raised exception",
                exc_info=True,
                extra={"stack": True},
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
        if getattr(settings, "IS_PROD", False):
            logger.error(
                "Question get results with segment in template tag raised exception",
                exc_info=True,
                extra={"stack": True},
            )
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

    default_colors = ["#e4002b", "#ff8200", "#ffd100", "#009a17", "#41b6e6", "#0050b5", "#d9d9d6"]

    org_colors = org.get_config("common.colors", "").upper().split(",")
    org_colors = [elt.strip() for elt in org_colors if elt.strip()]

    for elt in default_colors:
        if len(org_colors) >= 6:
            break
        if elt.upper() not in org_colors:
            org_colors.append(elt.upper())

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
    regions = UNICEF_REGIONS.copy()
    return dict(
        linked_orgs=linked_orgs,
        regions=regions,
        break_pos=min(len(linked_orgs) / 2, 9),
        STATIC_URL=settings.STATIC_URL,
        is_iorg=context["is_iorg"],
    )


@register.inclusion_tag("public/edit_content.html", takes_context=True)
def edit_content(context, reverse_name, reverse_arg=None, anchor_id="", extra_css_classes="", icon_color="dark"):
    request = context["request"]
    org = context["org"]

    url_args = []
    if reverse_arg:
        url_args.append(reverse_arg)

    edit_url = f"{org.build_host_link()}{reverse(reverse_name, args=url_args)}{anchor_id}"

    return dict(
        request=request,
        edit_url=edit_url,
        extra_css_classes=extra_css_classes,
        icon_color=icon_color,
        STATIC_URL=settings.STATIC_URL,
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
def is_select(field):
    return isinstance(field.field.widget, forms.Select)


@register.filter
def is_multiple_select(field):
    return isinstance(field.field.widget, forms.SelectMultiple)


@register.filter
def is_textarea(field):
    return isinstance(field.field.widget, forms.Textarea)


@register.filter
def is_input(field):
    return isinstance(
        field.field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.PasswordInput, forms.URLInput)
    )


@register.filter
def is_checkbox(field):
    return isinstance(field.field.widget, forms.CheckboxInput)


@register.filter
def is_multiple_checkbox(field):
    return isinstance(field.field.widget, forms.CheckboxSelectMultiple)


@register.filter
def is_radio(field):
    return isinstance(field.field.widget, forms.RadioSelect)


@register.filter
def is_file(field):
    return isinstance(field.field.widget, forms.FileInput)
