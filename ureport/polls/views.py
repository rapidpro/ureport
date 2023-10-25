# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import ast
import re
from datetime import timedelta

from django_redis import get_redis_connection

from django import forms
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_image_file_extension
from django.db.models.functions import Lower
from django.forms import ModelForm
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.timesince import timesince
from django.utils.translation import gettext_lazy as _

from dash.categories.fields import CategoryChoiceField
from dash.categories.models import Category, CategoryImage
from dash.orgs.models import OrgBackend
from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from dash.tags.models import Tag
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.utils import json_date_to_datetime

from .models import Poll, PollImage, PollQuestion, PollResponseCategory


class PollForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False)
    published = forms.BooleanField(required=False)
    backend = forms.ModelChoiceField(OrgBackend.objects.none(), required=False)
    title = forms.CharField(max_length=255, widget=forms.Textarea)
    category = CategoryChoiceField(Category.objects.none())
    category_image = forms.ModelChoiceField(CategoryImage.objects.none(), required=False)
    poll_tags = forms.CharField(widget=forms.SelectMultiple, required=False, help_text=_("Select tags for this poll"))

    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]

        super(PollForm, self).__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(org=self.org)

        self.fields["backend"].queryset = OrgBackend.objects.filter(org=self.org, is_active=True).order_by("slug")

        # only display category images for this org which are active
        self.fields["category_image"].queryset = CategoryImage.objects.filter(
            category__org=self.org, is_active=True
        ).order_by("category__name", "name")

    def clean(self):
        cleaned_data = self.cleaned_data

        poll_tags = cleaned_data.get("poll_tags", "[]")
        if poll_tags:
            poll_tags = ast.literal_eval(poll_tags)

        tags = []

        for tag in poll_tags:
            if tag.startswith("[NEW_TAG]_"):
                tags.append(dict(name=tag[10:], new=True))
            else:
                tag_obj = Tag.objects.filter(org=self.org, pk=tag).first()
                if tag_obj:
                    tags.append(dict(name=tag_obj.name, new=False))

        cleaned_data["poll_tags"] = tags

        if not self.org.backends.filter(is_active=True).exists():
            raise ValidationError(_("Your org does not have any API token configuration."))

        return cleaned_data

    class Meta:
        model = Poll
        fields = (
            "is_active",
            "published",
            "is_featured",
            "backend",
            "title",
            "category",
            "category_image",
            "poll_tags",
        )


class PollResponseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]
        super(PollResponseForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Poll
        fields = ("response_title", "response_author", "response_content")


class PollFlowForm(forms.ModelForm):
    flow_uuid = forms.ChoiceField(choices=[])
    poll_date = forms.DateTimeField(required=False)

    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]
        self.backend = kwargs["backend"]
        del kwargs["backend"]

        super(PollFlowForm, self).__init__(*args, **kwargs)

        # find all the flows on this org, create choices for those
        flows = self.org.get_flows(self.backend)
        self.fields["flow_uuid"].choices = [
            (f["uuid"], f["name"] + " (" + f.get("date_hint", "--") + ")")
            for f in sorted(flows.values(), key=lambda k: k["name"].lower().strip())
        ]

    def clean(self):
        cleaned_data = self.cleaned_data
        poll_date = cleaned_data.get("poll_date")
        flow_uuid = cleaned_data.get("flow_uuid")

        flows = self.org.get_flows(self.backend)
        flow = flows.get(flow_uuid)

        if not poll_date and flow:
            date = flow.get("created_on", None)
            if date:
                poll_date = json_date_to_datetime(date)

        if not poll_date:
            poll_date = timezone.now()

        cleaned_data["poll_date"] = poll_date
        return cleaned_data

    class Meta:
        model = Poll
        fields = ("flow_uuid", "poll_date")


class QuestionForm(ModelForm):
    """
    Validates that all included questions have titles.
    """

    def clean(self):
        cleaned = self.cleaned_data
        included_count = 0

        # look at all our included polls
        for key in cleaned.keys():
            match = re.match(r"ruleset_([\w\-]+)_include", key)

            # this field is being included
            if match and cleaned[key]:
                # get the title for it
                title_key = "ruleset_%s_title" % match.group(1)
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
        fields = ("id",)


class ActivePollMixin(OrgObjPermsMixin):
    def get_queryset(self):
        queryset = super(ActivePollMixin, self).get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_active=True)

        return queryset


class PollCRUDL(SmartCRUDL):
    model = Poll
    actions = (
        "create",
        "list",
        "update",
        "questions",
        "images",
        "responses",
        "pull_refresh",
        "poll_date",
        "poll_flow",
    )

    class PollDate(ActivePollMixin, SmartUpdateView):
        form_class = PollFlowForm
        title = _("Adjust poll date")
        success_url = "id@polls.poll_questions"
        fields = ("poll_date",)
        success_message = _("Your poll has been updated, now pick which questions to include.")

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.PollDate, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            kwargs["backend"] = self.object.backend
            return kwargs

    class PollFlow(ActivePollMixin, SmartUpdateView):
        form_class = PollFlowForm
        title = _("Configure flow")
        success_url = "id@polls.poll_poll_date"
        fields = ("flow_uuid",)
        success_message = _("Your poll has been configured, now adjust the poll date.")

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.PollFlow, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            kwargs["backend"] = self.object.backend
            return kwargs

        def pre_process(self, request, *args, **kwargs):
            obj = self.get_object()
            if obj.flow_uuid:
                return HttpResponseRedirect(reverse("polls.poll_poll_date", args=[obj.pk]))
            return None

        def pre_save(self, obj):
            obj = super(PollCRUDL.PollFlow, self).pre_save(obj)
            obj.org = self.request.org

            now = timezone.now()
            five_minutes_ago = now - timedelta(minutes=5)

            similar_poll = Poll.objects.filter(
                org=obj.org,
                flow_uuid=obj.flow_uuid,
                backend=obj.backend,
                is_active=True,
                published=True,
                created_on__gte=five_minutes_ago,
            ).first()
            if similar_poll:
                obj = similar_poll

            flow = obj.get_flow()

            date = flow.get("created_on", None)
            if date:
                flow_date = json_date_to_datetime(date)
            else:
                flow_date = timezone.now()

            obj.poll_date = flow_date
            return obj

        def post_save(self, obj):
            obj = super(PollCRUDL.PollFlow, self).post_save(obj)
            obj.update_or_create_questions(user=self.request.user)

            Poll.pull_poll_results_task(obj)
            return obj

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = PollForm
        success_url = "id@polls.poll_poll_flow"
        fields = ("is_featured", "backend", "title", "category", "category_image")
        success_message = _("Your poll has been created, now configure its flow.")

        def derive_fields(self):
            org = self.request.org

            backend_options = org.backends.filter(is_active=True).values_list("slug", flat=True)
            if len(backend_options) <= 1:
                return ("is_featured", "title", "category", "category_image", "poll_tags")
            return ("is_featured", "backend", "title", "category", "category_image", "poll_tags")

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Create, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)

            tags = Tag.objects.filter(org=self.org).order_by(Lower("name"))
            context["tags_data"] = [dict(id=tag.id, text=tag.name) for tag in tags]

            return context

        def pre_save(self, obj):
            obj = super(PollCRUDL.Create, self).pre_save(obj)
            org = self.request.org
            obj.org = org

            backend_options = org.backends.filter(is_active=True)
            if len(backend_options) == 1:
                obj.backend = backend_options[0]

            now = timezone.now()
            five_minutes_ago = now - timedelta(minutes=5)

            similar_poll = Poll.objects.filter(
                org=obj.org, flow_uuid="", backend=obj.backend, is_active=True, created_on__gte=five_minutes_ago
            ).first()
            if similar_poll:
                obj = similar_poll

            obj.poll_date = timezone.now()
            return obj

        def post_save(self, obj):
            cleaned_data = self.form.cleaned_data
            org = obj.org
            user = self.request.user

            tags = cleaned_data["poll_tags"]
            poll_tag_ids = []

            for tag_dict in tags:
                if tag_dict["new"]:
                    tag_obj = Tag.objects.create(org=org, name=tag_dict["name"], created_by=user, modified_by=user)
                else:
                    tag_obj = Tag.objects.filter(org=org, name=tag_dict["name"]).first()

                poll_tag_ids.append(tag_obj.pk)

            for tag in obj.tags.all():
                if tag not in poll_tag_ids:
                    obj.tags.remove(tag)

            for tag in Tag.objects.filter(id__in=poll_tag_ids):
                obj.tags.add(tag)

            Poll.find_main_poll(org)
            return obj

    class Images(ActivePollMixin, SmartUpdateView):
        success_url = "id@polls.poll_responses"
        title = _("Poll Images")
        success_message = _("Now enter any responses you'd like to feature. (if any)")

        def get_form(self):
            form = super(PollCRUDL.Images, self).get_form()
            form.fields.clear()

            idx = 1

            # add existing images
            for image in self.object.images.all().order_by("pk"):
                image_field_name = "image_%d" % idx
                image_field = forms.ImageField(
                    required=False,
                    initial=image.image,
                    label=_("Image %d") % idx,
                    help_text=_("Image to display on poll page and in previews. (optional)"),
                    validators=[validate_image_file_extension],
                )

                self.form.fields[image_field_name] = image_field
                idx += 1

            while idx <= 3:
                self.form.fields["image_%d" % idx] = forms.ImageField(
                    required=False,
                    label=_("Image %d") % idx,
                    help_text=_("Image to display on poll page and in previews (optional)"),
                    validators=[validate_image_file_extension],
                )
                idx += 1

            return form

        def post_save(self, obj):
            obj = super(PollCRUDL.Images, self).post_save(obj)

            # remove our existing images
            self.object.images.all().delete()

            # overwrite our new ones
            # TODO: this could probably be done more elegantly
            for idx in range(1, 4):
                image = self.form.cleaned_data.get("image_%d" % idx, None)

                if image:
                    PollImage.objects.create(
                        poll=self.object, image=image, created_by=self.request.user, modified_by=self.request.user
                    )

            return obj

    class Responses(ActivePollMixin, SmartUpdateView):
        form_class = PollResponseForm
        title = _("Poll Response")
        success_url = "@polls.poll_list"
        success_message = _("Your poll has been updated.")
        fields = ("response_title", "response_author", "response_content")

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Responses, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

    class Questions(ActivePollMixin, SmartUpdateView):
        success_url = "id@polls.poll_images"
        title = _("Poll Questions")
        form_class = QuestionForm
        success_message = _("Now set what images you want displayed on your poll page. (if any)")

        def derive_fields(self):
            questions = self.object.questions.all().select_related("flow_result")

            fields = []
            for question in questions:
                result_uuid = question.flow_result.result_uuid

                fields.append("ruleset_%s_include" % result_uuid)
                fields.append("ruleset_%s_label" % result_uuid)

                fields.append("ruleset_%s_color" % result_uuid)

                fields.append("ruleset_%s_hidden_charts" % result_uuid)

                fields.append("ruleset_%s_title" % result_uuid)

                categories = question.get_public_categories()
                for category in categories:
                    fields.append(f"ruleset_{result_uuid}_cat_label_{category.id}")
                    fields.append(f"ruleset_{result_uuid}_cat_display_{category.id}")

                fields.append("ruleset_%s_priority" % result_uuid)

            return fields

        def get_questions(self):
            return (
                self.object.questions.all()
                .select_related("flow_result", "poll", "poll__org")
                .order_by("-priority", "pk")
            )

        def get_form(self):
            form = super(PollCRUDL.Questions, self).get_form()
            form.fields.clear()

            # fetch this single flow so we load what rules are available
            questions = self.get_questions()

            initial = self.derive_initial()

            for question in questions:
                result_uuid = question.flow_result.result_uuid

                include_field_name = f"ruleset_{result_uuid}_include"
                include_field_initial = initial.get(include_field_name, False)
                include_field = forms.BooleanField(
                    label=_("Include"),
                    required=False,
                    initial=include_field_initial,
                    help_text=_("Whether to include this question in your public results"),
                )

                priority_field_name = f"ruleset_{result_uuid}_priority"
                priority_field_initial = initial.get(priority_field_name, None)
                priority_field = forms.IntegerField(
                    label=_("Priority"),
                    required=False,
                    initial=priority_field_initial,
                    help_text=_("The priority of this question on the poll page, higher priority comes first"),
                )

                label_field_name = f"ruleset_{result_uuid}_label"
                label_field_initial = initial.get(label_field_name, "")
                label_field = forms.CharField(
                    label=_("Ruleset Label"),
                    widget=forms.TextInput(attrs={"readonly": "readonly"}),
                    required=False,
                    initial=label_field_initial,
                    help_text=_("The label of the ruleset from RapidPro"),
                )

                title_field_name = f"ruleset_{result_uuid}_title"
                title_field_initial = initial.get(title_field_name, "")
                title_field = forms.CharField(
                    label=_("Title"),
                    widget=forms.Textarea,
                    required=False,
                    initial=title_field_initial,
                    help_text=_("The question posed to your audience, will be displayed publicly"),
                )

                color_field_name = f"ruleset_{result_uuid}_color"
                color_field_initial = initial.get(color_field_name, "")
                color_field = forms.ChoiceField(
                    label=_("Color Choice"),
                    choices=PollQuestion.QUESTION_COLOR_CHOICES,
                    required=False,
                    initial=color_field_initial,
                    help_text=_("The color to use for the question block will be displayed publicly"),
                )

                hidden_charts_field_name = f"ruleset_{result_uuid}_hidden_charts"
                hidden_charts_field_initial = initial.get(hidden_charts_field_name, "")
                hidden_charts_field = forms.ChoiceField(
                    label=_("Hidden Charts Choice"),
                    choices=PollQuestion.QUESTION_HIDDEN_CHARTS_CHOICES,
                    required=False,
                    initial=hidden_charts_field_initial,
                    help_text=_("Choose the charts breakdown to hide to for this question to the public"),
                )

                self.form.fields[include_field_name] = include_field
                self.form.fields[priority_field_name] = priority_field
                self.form.fields[label_field_name] = label_field
                self.form.fields[title_field_name] = title_field
                self.form.fields[color_field_name] = color_field
                self.form.fields[hidden_charts_field_name] = hidden_charts_field

                categories = question.get_public_categories()
                for idx, category in enumerate(categories):
                    cat_label_field_name = f"ruleset_{result_uuid}_cat_label_{category.id}"
                    cat_label_field_initial = initial.get(cat_label_field_name, "")
                    cat_label_field = forms.CharField(
                        label=_(f"Category {idx+1}"),
                        widget=forms.TextInput(attrs={"readonly": "readonly"}),
                        required=False,
                        initial=cat_label_field_initial,
                        help_text=_("The label of the category from backend(such as RapidPro)"),
                    )

                    cat_display_field_name = f"ruleset_{result_uuid}_cat_display_{category.id}"
                    cat_display_field_initial = initial.get(cat_display_field_name, "")
                    cat_display_field = forms.CharField(
                        label=_(f"Display {idx+1}"),
                        required=False,
                        initial=cat_display_field_initial,
                        help_text=_("The label to display of the category on the public site"),
                    )

                    self.form.fields[cat_label_field_name] = cat_label_field
                    self.form.fields[cat_display_field_name] = cat_display_field

            return self.form

        def save(self, obj):
            data = self.form.cleaned_data
            poll = self.object
            questions = self.get_questions()

            # for each question
            for question in questions:
                result_uuid = question.flow_result.result_uuid

                included = data.get(f"ruleset_{result_uuid}_include", False)
                priority = data.get(f"ruleset_{result_uuid}_priority", None)
                if not priority:
                    priority = 0

                title = data[f"ruleset_{result_uuid}_title"]

                color_choice = data[f"ruleset_{result_uuid}_color"]

                hidden_charts_choice = data[f"ruleset_{result_uuid}_hidden_charts"]

                PollQuestion.objects.filter(poll=poll, flow_result__result_uuid=result_uuid).update(
                    is_active=included,
                    title=title,
                    priority=priority,
                    color_choice=color_choice,
                    hidden_charts=hidden_charts_choice,
                )

                categories = question.get_public_categories()
                for category in categories:
                    flow_category = category.flow_result_category.category
                    category_id = category.id

                    category_displayed_data = data[f"ruleset_{result_uuid}_cat_display_{category_id}"]

                    try:
                        category_displayed = strip_tags(category_displayed_data)
                    except NotImplementedError:
                        category_displayed = None

                    if not category_displayed:
                        category_displayed = flow_category

                    PollResponseCategory.objects.filter(id=category_id).update(category_displayed=category_displayed)

            return self.object

        def post_save(self, obj):
            obj = super(PollCRUDL.Questions, self).post_save(obj)

            obj.update_questions_results_cache_task()

            Poll.find_main_poll(obj.org)
            return obj

        def derive_initial(self):
            initial = dict()
            questions = self.get_questions()

            for question in questions:
                result_uuid = question.flow_result.result_uuid
                result_name = question.flow_result.result_name

                initial["ruleset_%s_include" % result_uuid] = question.is_active
                initial["ruleset_%s_priority" % result_uuid] = question.priority
                initial["ruleset_%s_label" % result_uuid] = result_name
                initial["ruleset_%s_title" % result_uuid] = question.title
                initial["ruleset_%s_color" % result_uuid] = question.color_choice
                initial["ruleset_%s_hidden_charts" % result_uuid] = question.hidden_charts

                categories = question.get_public_categories()
                for category in categories:
                    flow_category = category.flow_result_category.category
                    initial[f"ruleset_{result_uuid}_cat_label_{category.id}"] = flow_category
                    initial[f"ruleset_{result_uuid}_cat_display_{category.id}"] = (
                        category.category_displayed or flow_category
                    )

            return initial

    class List(OrgPermsMixin, SmartListView):
        search_fields = ("title__icontains",)
        fields = (
            "title",
            "poll_date",
            "category",
            "questions",
            "opinion_response",
            "sync_status",
            "created_on",
            "tags",
            "preview",
        )
        link_fields = ("title", "poll_date", "questions", "opinion_response", "images")
        default_order = ("-created_on", "id")
        paginate_by = 10

        def get_queryset(self):
            queryset = super(PollCRUDL.List, self).get_queryset().filter(org=self.request.org)
            if not self.request.user.is_superuser:
                queryset = queryset.filter(is_active=True)

            return queryset

        def get_context_data(self, **kwargs):
            context = super(PollCRUDL.List, self).get_context_data(**kwargs)

            org = self.request.org

            unsynced_polls = (
                Poll.objects.filter(org=org, has_synced=False).exclude(is_active=False).exclude(flow_uuid="")
            )
            context["unsynced_polls"] = unsynced_polls

            context["main_poll"] = Poll.get_main_poll(org)
            context["other_polls"] = Poll.get_other_polls(org)
            context["recent_polls"] = Poll.get_recent_polls(org)

            return context

        def get_sync_status(self, obj):
            if obj.has_synced:
                r = get_redis_connection()
                key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (obj.org.pk, obj.flow_uuid)
                if r.get(key):
                    return _("Scheduled Sync currently in progress...")

                last_synced = cache.get(Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (obj.org.pk, obj.flow_uuid), None)
                if last_synced:
                    return _(
                        "Last results synced %(time)s ago" % dict(time=timesince(json_date_to_datetime(last_synced)))
                    )

                # we know we synced do not check the the progress since that is slow
                return _("Synced")

            sync_progress = obj.get_sync_progress()
            return _(f"Sync currently in progress... {sync_progress:.1f}%")

        def get_questions(self, obj):
            return obj.get_questions().count()

        def get_images(self, obj):
            return obj.get_images().count()

        def get_opinion_response(self, obj):
            return obj.response_title or "--"

        def get_category(self, obj):
            return obj.category.name

        def lookup_field_link(self, context, field, obj):
            if field == "questions":
                return reverse("polls.poll_questions", args=[obj.pk])
            elif field == "poll_date":
                return reverse("polls.poll_poll_date", args=[obj.pk])
            elif field == "images":
                return reverse("polls.poll_images", args=[obj.pk])
            elif field == "preview":
                return reverse("public.opinion_preview", args=[obj.pk])
            elif field == "opinion_response":
                return reverse("polls.poll_responses", args=[obj.pk])
            else:
                return super(PollCRUDL.List, self).lookup_field_link(context, field, obj)

    class Update(ActivePollMixin, SmartUpdateView):
        form_class = PollForm
        fields = ("is_active", "is_featured", "title", "category", "category_image", "poll_tags")
        success_url = "id@polls.poll_poll_flow"

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("is_active", "published", "is_featured", "title", "category", "category_image", "poll_tags")
            return ("published", "is_featured", "title", "category", "category_image", "poll_tags")

        def derive_title(self):
            obj = self.get_object()
            flows = obj.org.get_flows(obj.backend)

            flow = flows.get(obj.flow_uuid, dict())

            flow_name = flow.get("name", "")
            flow_date_hint = flow.get("date_hint", "")

            return _(f"Edit Poll for flow [{flow_name} ({flow_date_hint})]")

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            obj = self.get_object()
            org = obj.org

            tags = Tag.objects.filter(org=org).order_by(Lower("name"))
            tags_data = [dict(id=tag.id, text=tag.name) for tag in tags]
            context["tags_data"] = tags_data

            context["poll_tags"] = [tag.id for tag in obj.tags.all()]

            return context

        def get_form_kwargs(self):
            kwargs = super(PollCRUDL.Update, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

        def post_save(self, obj):
            obj = super(PollCRUDL.Update, self).post_save(obj)
            obj.update_or_create_questions(user=self.request.user)

            cleaned_data = self.form.cleaned_data
            org = obj.org
            user = self.request.user

            tags = cleaned_data["poll_tags"]
            poll_tag_ids = []

            for tag_dict in tags:
                if tag_dict["new"]:
                    tag_obj = Tag.objects.create(org=org, name=tag_dict["name"], created_by=user, modified_by=user)
                else:
                    tag_obj = Tag.objects.filter(org=org, name=tag_dict["name"]).first()

                poll_tag_ids.append(tag_obj.pk)

            for tag in obj.tags.all():
                if tag not in poll_tag_ids:
                    obj.tags.remove(tag)

            for tag in Tag.objects.filter(id__in=poll_tag_ids):
                obj.tags.add(tag)

            Poll.find_main_poll(org)
            return obj

    class PullRefresh(SmartUpdateView):
        fields = ()
        success_url = "@polls.poll_list"
        success_message = None

        def post_save(self, obj):
            poll = self.get_object()
            poll.pull_refresh_task()
            self.success_message = _("Scheduled a pull refresh for poll #%(poll_id)d on org #%(org_id)d") % dict(
                poll_id=poll.pk, org_id=poll.org_id
            )
