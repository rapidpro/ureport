from django import forms
from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from smartmin.views import SmartCRUDL, SmartCreateView, SmartListView, SmartUpdateView
from .models import Category, CategoryImage

class CategoryImageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.org = kwargs['org']
        del kwargs['org']

        super(CategoryImageForm, self).__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(org=self.org)

    category = forms.ModelChoiceField(Category.objects.filter(id__lte=-1))

    class Meta:
        model = CategoryImage
        fields = ('is_active', 'name', 'category', 'image')

class CategoryCRUDL(SmartCRUDL):
    model = Category
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('is_active', 'name')

    class List(OrgPermsMixin, SmartListView):
        fields = ('name', 'modified_on', 'created_on')

        def get_queryset(self, **kwargs):
            queryset = super(CategoryCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset


    class Create(OrgPermsMixin, SmartCreateView):

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('name',  'org')
            return ('name', )

        def pre_save(self, obj):
            obj = super(CategoryCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            return obj

class CategoryImageCRUDL(SmartCRUDL):
    model = CategoryImage
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = CategoryImageForm
        fields = ('is_active', 'name', 'category', 'image')

        def get_object_org(self):
            return self.get_object().category.org

        def get_form_kwargs(self):
            kwargs = super(CategoryImageCRUDL.Update, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs

    class List(OrgPermsMixin, SmartListView):
        fields = ('name', 'modified_on', 'created_on')

        def get_queryset(self, **kwargs):
            queryset = super(CategoryImageCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(category__org=self.derive_org())

            return queryset

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = CategoryImageForm
        fields = ('name', 'category', 'image')

        def get_form_kwargs(self):
            kwargs = super(CategoryImageCRUDL.Create, self).get_form_kwargs()
            kwargs['org'] = self.request.org
            return kwargs