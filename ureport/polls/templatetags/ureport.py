from django import template
from django.core.urlresolvers import reverse
from django.template import TemplateSyntaxError
from django.template.defaultfilters import stringfilter
from django.conf import settings

register = template.Library()

@register.filter
def reporter_count(org):
    if not org:
        return None

    reporter_group = org.get_config('reporter_group')
    api = org.get_api()

    if reporter_group:
        group = api.get_group(reporter_group)
        if group:
            return group['size']

    return 0

@register.filter
def get_range(value):
    return range(value)

@register.filter
def config(org, name):
    if not org:
        return None

    return org.get_config(name)

@register.filter
def org_color(org, index):
    if not org:
        return None

    org_colors = org.get_config('colors')

    if org_colors:
       org_colors = org_colors.split(',')
    else:
        if org.get_config('primary_color') and org.get_config('secondary_color'):
            org_colors = [org.get_config('primary_color').strip(), org.get_config('secondary_color').strip()]
        else:
            org_colors = [getattr(settings, 'UREPORT_DEFAULT_PRIMARY_COLOR'), getattr(settings, 'UREPORT_DEFAULT_SECONDARY_COLOR')]

    return org_colors[int(index) % len(org_colors)].strip()


@register.filter
def transparency(color, alpha):
    if not color:
        return color

    if color[0] == '#':
        color = color[1:]

    if len(color) != 6:
        raise TemplateSyntaxError("add_transparency expect a long hexadecimal color, got: [%s]" % color)

    rgb_color = [ord(c) for c in color.decode('hex')]
    rgb_color.append(alpha)

    return "rgba(%s, %s, %s, %s)" % tuple(rgb_color)


def lessblock(parser, token):
    args = token.split_contents()
    if len(args) != 1:
        raise TemplateSyntaxError("lessblock tag takes no arguments, got: [%s]" % ",".join(args))

    nodelist = parser.parse(('endlessblock',))
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


class RenderOptionalPages(template.Node):
    def render(self, context):
        html = ''
        for optional_page in getattr(settings, 'OPTIONAL_PUBLIC_PAGES', []):
            app = optional_page[1].split('.')[-1]
            html += '<span>|<a class="primary-color" href="%s"> %s </a></span>' % (
                reverse('%s.index' % app), app.capitalize())
        return html


@register.tag(name="add_optional_pages")
def get_optional_pages(parser, token):
    return RenderOptionalPages()
