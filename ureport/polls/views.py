from dash.api import API
from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from django import forms
from django.core.urlresolvers import reverse
from ureport.categories.models import Category
from .models import Poll, PollQuestion, FeaturedResponse
from smartmin.views import SmartCRUDL, SmartCreateView, SmartListView, SmartUpdateView
from django.utils.translation import ugettext_lazy as _

class PollForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.org = kwargs['org']
        del kwargs['org']

        super(PollForm, self).__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(org=self.org)

        # find all the flows on this org, create choices for those
        api = self.org.get_api()
        flows = api.get_flows()
        self.fields['flow_id'].choices = [(f['flow'], f['name']) for f in flows]


    is_active = forms.BooleanField(required=False)
    flow_id = forms.ChoiceField(choices=[])
    title = forms.CharField(max_length=255, widget=forms.Textarea)
    category = forms.ModelChoiceField(Category.objects.filter(id__lte=-1))

    class Meta:
        model = Poll
        fields = ('is_active', 'is_featured', 'flow_id', 'title', 'category', 'image')

class FeaturedResponseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.org = kwargs['org']
        del kwargs['org']

        super(FeaturedResponseForm, self).__init__(*args, **kwargs)
        self.fields['poll'].queryset = Poll.objects.filter(org=self.org)

    poll = forms.ModelChoiceField(Poll.objects.filter(id__lte=-1))
    message = forms.CharField(max_length=255, widget=forms.Textarea,
                              help_text=_("The message sent by the U-reporter you want to feature"))

    class Meta:
        model = FeaturedResponse
        fields = ('is_active', 'poll', 'location', 'reporter', 'message')

class PollCRUDL(SmartCRUDL):
    model = Poll
    actions = ('create', 'list', 'update', 'questions')

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = PollForm
        success_url = 'id@polls.poll_questions'

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Create, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs

        def pre_save(self, obj):
            obj = super(PollCRUDL.Create, self).pre_save(obj)
            obj.org = self.request.org
            return obj

    class Questions(OrgPermsMixin, SmartUpdateView):
        success_url = '@polls.poll_list'
        title = _("Poll Questions")

        def get_rulesets(self):
            api = self.object.org.get_api()
            rulesets = api.get_flow(self.object.flow_id)['rulesets']
            return rulesets

        def derive_fields(self):
            rulesets = self.get_rulesets()

            fields = []
            for ruleset in rulesets:
                fields.append('ruleset_%d_include' % ruleset['id'])
                fields.append('ruleset_%d_title' % ruleset['id'])

            return fields

        def get_form(self, form_class):
            form = super(PollCRUDL.Questions, self).get_form(form_class)
            form.fields.clear()

            # fetch this single flow so we load what rules are available
            rulesets = self.get_rulesets()

            for ruleset in rulesets:
                include_field = forms.BooleanField(label=_("Include"), required=False, initial=False,
                                                   help_text=_("Whether to include this question in your public results"))
                include_field_name = 'ruleset_%d_include' % ruleset['id']
                title_field = forms.CharField(label=_("Title"), initial=ruleset['label'], widget=forms.Textarea,
                                              help_text=_("The question posed to your audience, will be displayed publicly"))
                title_field_name = 'ruleset_%d_title' % ruleset['id']

                self.form.fields[include_field_name] = include_field
                self.form.fields[title_field_name] = title_field

            return self.form

        def save(self, obj):
            rulesets = self.get_rulesets()
            data = self.form.cleaned_data
            poll = self.object

            # for each ruleset
            for ruleset in rulesets:
                rid = ruleset['id']

                included = data.get('ruleset_%d_include' % rid, False)
                title = data['ruleset_%d_title' % rid]
                existing = PollQuestion.objects.filter(poll=poll, ruleset_id=rid).first()

                if included:
                    # already one of our questions, just update our title
                    if existing:
                        existing.title = title
                        existing.save()

                    # doesn't exist, let's add it
                    else:
                        poll.questions.create(ruleset_id=rid, title=title,
                                              created_by=self.request.user, modified_by=self.request.user)

                # not included, remove it from our poll
                else:
                    PollQuestion.objects.filter(poll=poll, ruleset_id=rid).delete()

            return self.object

        def derive_initial(self):
            initial = dict()

            for question in self.object.questions.all():
                initial['ruleset_%d_include' % question.ruleset_id] = True
                initial['ruleset_%d_title' % question.ruleset_id] = question.title

            return initial

    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'category', 'questions', 'created_on')
        link_fields = ('title', 'questions')

        def get_queryset(self):
            queryset = super(PollCRUDL.List, self).get_queryset().filter(org=self.request.org)
            return queryset

        def get_questions(self, obj):
            q_count = obj.questions.count()

            if not q_count:
                return _("No Questions")
            elif q_count == 1:
                return _("1 Question")
            else:
                return _("%d Questions") % q_count

        def lookup_field_link(self, context, field, obj):
            if field == 'questions':
                return reverse('polls.poll_questions', args=[obj.pk])
            else:
                return super(PollCRUDL.List, self).lookup_field_link(context, field, obj)

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = PollForm
        fields = ('is_active', 'is_featured', 'flow_id', 'title', 'category', 'image')

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Update, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs


class FeaturedResponseCRUDL(SmartCRUDL):
    model = FeaturedResponse
    actions = ('create', 'list', 'update')

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = FeaturedResponseForm
        fields = ('poll', 'location', 'reporter', 'message')

        def get_form_kwargs(self):
            kwargs = super(FeaturedResponseCRUDL.Create, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs

    class List(OrgPermsMixin, SmartListView):
        fields = ('poll', 'location', 'message')

        def get_queryset(self):
            queryset = super(FeaturedResponseCRUDL.List, self).get_queryset().filter(poll__org=self.request.org)
            return queryset

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = FeaturedResponseForm

        def get_object_org(self):
            return self.get_object().poll.org

        def get_form_kwargs(self):
            kwargs = super(FeaturedResponseCRUDL.Update, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs
