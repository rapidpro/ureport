from django import forms
import pycountry
from smartmin.views import SmartCRUDL, SmartListView, SmartCreateView, SmartUpdateView
from .models import CountryAlias


class CountryAliasForm(forms.ModelForm):

    def clean_name(self):
        name = self.cleaned_data['name']
        return CountryAlias.name_stemming(name)

    class Meta:
        model = CountryAlias
        fields = ('is_active', 'name', 'country')


class CountryAliasCRUDL(SmartCRUDL):
    model = CountryAlias
    actions = ('list', 'create', 'update')

    class List(SmartListView):
        fields = ('country', 'name', 'modified_on')
        default_order = ('country',)
        search_fields = ('country__iexact', 'name__icontains')

        def get_country(self, obj):
            return "%s (%s)" % (obj.country.name.strip(), obj.country.code)

    class Create(SmartCreateView):
        form_class = CountryAliasForm
        fields = ('name', 'country')

    class Update(SmartUpdateView):
        form_class = CountryAliasForm
        fields = ('is_active', 'name', 'country')