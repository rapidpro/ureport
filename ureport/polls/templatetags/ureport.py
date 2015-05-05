from __future__ import absolute_import

from dash.orgs.models import Org
from django import template
from django.core.urlresolvers import reverse
from django.template import TemplateSyntaxError
from django.template.defaultfilters import stringfilter
from django.conf import settings
from ureport.utils import get_linked_orgs

register = template.Library()

@register.filter
def question_results(question):
    if not question:
        return None

    try:
        results = question.get_results()
        return results[0]
    except:
        import traceback
        traceback.print_exc()
        return None

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
def age_stats(org):
    if not org:
        return None

    try:
        born_field = org.get_config('born_label')
        api_data = org.get_contact_field_results(born_field, None)
        output_data = org.organize_categories_data(born_field, api_data)[0]

        total = output_data['set']
        for category in output_data['categories']:
            if category['count']:
                category['percentage'] = int(category['count'] * 100 / total)
            else:
                category['percentage'] = 0

        return output_data['categories']

    except:
        # we never want to blow up the view
        import traceback
        traceback.print_exc()

    return None

@register.filter
def gender_stats(org):
    if not org:
        return None

    gender_field = org.get_config('gender_label')
    gender_data = None
    if gender_field:
        gender_data = org.get_contact_field_results(gender_field, None)

    if gender_data:
        try:
            # not segmented, so just get the first segment
            gender_data = gender_data[0]
            male_label = org.get_config('male_label').lower()
            female_label = org.get_config('female_label').lower()

            if male_label and female_label:
                male_count = 0
                female_count = 0

                for category in gender_data['categories']:
                    if category['label'].lower() == male_label:
                        male_count += category['count']
                    elif category['label'].lower() == female_label:
                        female_count += category['count']

                total_count = male_count + female_count
                male_percentage = 0
                if male_count > 0:
                    male_percentage = int(male_count * 100.0 / total_count)
                female_percentage = 100 - male_percentage
                return dict(total_count=total_count,
                            male_count=male_count, male_percentage=male_percentage,
                            female_count=female_count, female_percentage=female_percentage)
        except:
            # we never want to blow up the page, but let's log what happened
            import traceback
            traceback.print_exc()

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

@register.inclusion_tag('public/org_flags.html')
def show_org_flags():
    linked_orgs = get_linked_orgs()
    return dict(linked_orgs=linked_orgs, STATIC_URL=settings.STATIC_URL)