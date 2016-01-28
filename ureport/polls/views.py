from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from django import forms
from django.core.urlresolvers import reverse
from dash.categories.models import Category, CategoryImage
from django.utils import timezone

from ureport.utils import json_date_to_datetime
from .models import Poll, PollQuestion, FeaturedResponse, PollImage, CACHE_ORG_FLOWS_KEY
from smartmin.views import SmartCRUDL, SmartCreateView, SmartListView, SmartUpdateView
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.forms import ModelForm
import re


class PollForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.org = kwargs['org']
        del kwargs['org']

        super(PollForm, self).__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(org=self.org)

        # find all the flows on this org, create choices for those
        flows = self.org.get_flows()

        self.fields['flow_uuid'].choices = [(f['uuid'], f['name'] + " (" + f.get('date_hint', "--") + ")") for f in sorted(flows.values(), key=lambda k:k['name'].lower().strip())]

        # only display category images for this org which are active
        self.fields['category_image'].queryset = CategoryImage.objects.filter(category__org=self.org, is_active=True).order_by('category__name', 'name')

    is_active = forms.BooleanField(required=False)
    flow_uuid = forms.ChoiceField(choices=[])
    poll_date = forms.DateTimeField(required=False)
    title = forms.CharField(max_length=255, widget=forms.Textarea)
    category = forms.ModelChoiceField(Category.objects.filter(id__lte=-1))
    category_image = forms.ModelChoiceField(CategoryImage.objects.filter(id__lte=0), required=False)

    def clean(self):
        cleaned_data = self.cleaned_data
        poll_date = cleaned_data.get('poll_date')
        flow_uuid = cleaned_data.get('flow_uuid')

        flows = self.org.get_flows()
        flow = flows.get(flow_uuid)

        if not poll_date and flow:
            date = flow.get('created_on', None)
            if date:
                poll_date = json_date_to_datetime(date)

        if not poll_date:
            poll_date = timezone.now()

        cleaned_data['poll_date'] = poll_date
        return cleaned_data

    class Meta:
        model = Poll
        fields = ('is_active', 'is_featured', 'flow_uuid', 'title', 'poll_date', 'category', 'category_image')


class QuestionForm(ModelForm):
    """
    Validates that all included questions have titles.
    """
    def clean(self):
        cleaned = self.cleaned_data
        included_count = 0

        # look at all our included polls
        for key in cleaned.keys():
            match = re.match('ruleset_([\w\-]+)_include', key)

            # this field is being included
            if match and cleaned[key]:
                # get the title for it
                title_key = 'ruleset_%s_title' % match.group(1)
                if not cleaned[title_key]:
                    raise ValidationError(_("You must include a title for every included question."))

                if len(cleaned[title_key]) > 255:
                    raise ValidationError(_("Title too long. The max limit is 255 characters for each title"))

                included_count += 1

        if not included_count:
            raise ValidationError(_("You must include at least one poll question."))

        return cleaned

    class Meta:
        model = Poll
        fields = ('id',)


class PollCRUDL(SmartCRUDL):
    model = Poll
    actions = ('create', 'list', 'update', 'questions', 'images', 'responses')

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = PollForm
        success_url = 'id@polls.poll_questions'
        fields = ('is_featured', 'flow_uuid', 'title', 'category', 'category_image')
        success_message = _("Your poll has been created, now pick which questions to include.")

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Create, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs

        def pre_save(self, obj):
            obj = super(PollCRUDL.Create, self).pre_save(obj)
            obj.org = self.request.org
            flow = obj.get_flow()

            date = flow.get('created_on', None)
            if date:
                flow_date = json_date_to_datetime(date)
            else:
                flow_date = timezone.now()

            obj.poll_date = flow_date
            return obj

    class Images(OrgObjPermsMixin, SmartUpdateView):
        success_url = 'id@polls.poll_responses'
        title = _("Poll Images")
        success_message = _("Now enter any responses you'd like to feature. (if any)")

        def get_form(self, form_class):
            form = super(PollCRUDL.Images, self).get_form(form_class)
            form.fields.clear()

            idx = 1

            # add existing images
            for image in self.object.images.all().order_by('pk'):
                image_field_name = 'image_%d' % idx
                image_field = forms.ImageField(required=False, initial=image.image, label=_("Image %d") % idx,
                                               help_text=_("Image to display on poll page and in previews. (optional)"))

                self.form.fields[image_field_name] = image_field
                idx += 1

            while idx <= 3:
                self.form.fields['image_%d' % idx] = forms.ImageField(required=False, label=_("Image %d") % idx,
                                                                      help_text=_("Image to display on poll page and in previews (optional)"))
                idx += 1

            return form

        def post_save(self, obj):
            obj = super(PollCRUDL.Images, self).post_save(obj)

            # remove our existing images
            self.object.images.all().delete()

            # overwrite our new ones
            # TODO: this could probably be done more elegantly
            for idx in range(1, 4):
                image = self.form.cleaned_data.get('image_%d' % idx, None)

                if image:
                    PollImage.objects.create(poll=self.object, image=image,
                                             created_by=self.request.user, modified_by=self.request.user)

            return obj

    class Responses(OrgObjPermsMixin, SmartUpdateView):
        success_url = '@polls.poll_list'
        title = _("Featured Poll Responses")
        success_message = _("Your poll has been updated.")

        def get_form(self, form_class):
            form = super(PollCRUDL.Responses, self).get_form(form_class)
            form.fields.clear()

            existing_responses = list(self.object.featured_responses.all().order_by('pk'))

            # add existing responses
            for idx in range(1, 4):
                if existing_responses:
                    response = existing_responses.pop(0)
                else:
                    response = None

                # reporter, location, response
                reporter_args = dict(max_length=64, required=False,
                                     label=_("Response %d Reporter") % idx, help_text=_("The name or alias of the responder."))
                if response: reporter_args['initial'] = response.reporter
                self.form.fields['reporter_%d' % idx] = forms.CharField(**reporter_args)

                location_args = dict(max_length=64, required=False,
                                     label=_("Response %d Location") % idx, help_text=_("The location of the responder."))
                if response: location_args['initial'] = response.location
                self.form.fields['location_%d' % idx] = forms.CharField(**location_args)

                message_args = dict(max_length=255, required=False, widget=forms.Textarea,
                                    label=_("Response %d Message") % idx, help_text=_("The text of the featured response."))
                if response: message_args['initial'] = response.message
                self.form.fields['message_%d' % idx] = forms.CharField(**message_args)

            return form

        def post_save(self, obj):
            obj = super(PollCRUDL.Responses, self).post_save(obj)

            # remove our existing responses
            self.object.featured_responses.all().delete()

            # overwrite our new ones
            for idx in range(1, 4):
                location = self.form.cleaned_data.get('location_%d' % idx, None)
                reporter = self.form.cleaned_data.get('reporter_%d' % idx, None)
                message = self.form.cleaned_data.get('message_%d' % idx, None)

                if location and reporter and message:
                    FeaturedResponse.objects.create(poll=self.object,
                                                    location=location, reporter=reporter, message=message,
                                                    created_by=self.request.user, modified_by=self.request.user)
            return obj

    class Questions(OrgObjPermsMixin, SmartUpdateView):
        success_url = 'id@polls.poll_images'
        title = _("Poll Questions")
        form_class = QuestionForm
        success_message = _("Now set what images you want displayed on your poll page. (if any)")

        def get_rulesets(self):
            flow = self.object.get_flow()
            rulesets = []
            if flow:
                rulesets = flow['rulesets']
            return rulesets

        def derive_fields(self):
            rulesets = self.get_rulesets()

            fields = []
            for ruleset in rulesets:
                fields.append('ruleset_%s_include' % ruleset['uuid'])
                fields.append('ruleset_%s_title' % ruleset['uuid'])

            return fields

        def get_form(self, form_class):
            form = super(PollCRUDL.Questions, self).get_form(form_class)
            form.fields.clear()

            # fetch this single flow so we load what rules are available
            rulesets = self.get_rulesets()

            initial = self.derive_initial()

            for ruleset in rulesets:
                include_field_name = 'ruleset_%s_include' % ruleset['uuid']
                include_field_initial = initial.get(include_field_name, False)
                include_field = forms.BooleanField(label=_("Include"), required=False, initial=include_field_initial,
                                                   help_text=_("Whether to include this question in your public results"))

                title_field_name = 'ruleset_%s_title' % ruleset['uuid']
                title_field_initial = initial.get(title_field_name, ruleset['label'])
                title_field = forms.CharField(label=_("Title"), widget=forms.Textarea, required=False, initial=title_field_initial,
                                              help_text=_("The question posed to your audience, will be displayed publicly"))


                self.form.fields[include_field_name] = include_field
                self.form.fields[title_field_name] = title_field

            return self.form

        def save(self, obj):
            rulesets = self.get_rulesets()
            data = self.form.cleaned_data
            poll = self.object

            # for each ruleset
            for ruleset in rulesets:
                r_uuid = ruleset['uuid']

                included = data.get('ruleset_%s_include' % r_uuid, False)
                title = data['ruleset_%s_title' % r_uuid]
                existing = PollQuestion.objects.filter(poll=poll, ruleset_uuid=r_uuid).first()

                if included:
                    # already one of our questions, just update our title
                    if existing:
                        existing.title = title
                        existing.save()

                    # doesn't exist, let's add it
                    else:
                        poll.questions.create(ruleset_uuid=r_uuid, title=title,
                                              created_by=self.request.user, modified_by=self.request.user)

                # not included, remove it from our poll
                else:
                    PollQuestion.objects.filter(poll=poll, ruleset_uuid=r_uuid).delete()

            # delete poll questions for old rulesets
            PollQuestion.objects.filter(poll=poll).exclude(ruleset_uuid__in=[ruleset['uuid'] for ruleset in rulesets]).delete()

            return self.object

        def post_save(self, obj):
            obj = super(PollCRUDL.Questions, self).post_save(obj)

            # clear our cache of featured polls
            Poll.clear_brick_polls_cache(obj.org)

            Poll.fetch_poll_results_task(obj)

            return obj

        def derive_initial(self):
            initial = dict()

            for question in self.object.questions.all():
                initial['ruleset_%s_include' % question.ruleset_uuid] = True
                initial['ruleset_%s_title' % question.ruleset_uuid] = question.title

            return initial

    class List(OrgPermsMixin, SmartListView):
        search_fields = ('title__icontains',)
        fields = ('title', 'category', 'questions', 'featured_responses', 'images', 'created_on')
        link_fields = ('title', 'questions', 'featured_responses', 'images')
        default_order = ('-created_on', 'id')

        def get_queryset(self):
            queryset = super(PollCRUDL.List, self).get_queryset().filter(org=self.request.org)
            return queryset

        def get_questions(self, obj):
            return obj.get_questions().count()

        def get_images(self, obj):
            return obj.get_images().count()

        def get_featured_responses(self, obj):
            return obj.get_featured_responses().count()

        def lookup_field_link(self, context, field, obj):
            if field == 'questions':
                return reverse('polls.poll_questions', args=[obj.pk])
            elif field == 'images':
                return reverse('polls.poll_images', args=[obj.pk])
            elif field == 'featured_responses':
                return reverse('polls.poll_responses', args=[obj.pk])
            else:
                return super(PollCRUDL.List, self).lookup_field_link(context, field, obj)

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = PollForm
        fields = ('is_active', 'is_featured', 'flow_uuid', 'title', 'poll_date', 'category', 'category_image')

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Update, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs
