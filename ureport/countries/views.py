import pycountry
from smartmin.views import SmartCRUDL, SmartListView
from .models import CountryAlias

class CountryAliasCRUDL(SmartCRUDL):
    model = CountryAlias
    actions = ('list', 'create', 'update')

    class List(SmartListView):
        fields = ('country', 'name', 'modified_on')
        default_order = ('country',)
        search_fields = ('country__iexact', 'name__icontains')

        def get_country(self, obj):
            return "%s (%s)" % (obj.country.name.strip(), obj.country.code)
