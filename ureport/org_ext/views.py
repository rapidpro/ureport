from __future__ import absolute_import, unicode_literals

from dash.orgs.models import Org
from dash.orgs.views import OrgCRUDL, InferOrgMixin, OrgPermsMixin, SmartUpdateView
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _

from smartmin.views import SmartCRUDL
from ureport.org_ext import OrgCache, refresh_caches


class OrgExtCRUDL(SmartCRUDL):
    actions = ('create', 'list', 'update', 'choose', 'home', 'edit', 'manage_accounts', 'create_login', 'join',
               'chooser', 'refresh_cache')
    model = Org

    class Create(OrgCRUDL.Create):
        pass

    class List(OrgCRUDL.List):
        pass

    class Update(OrgCRUDL.Update):
        pass

    class Choose(OrgCRUDL.Choose):
        def pre_process(self, request, *args, **kwargs):
            if self.request.user.is_authenticated():
                if self.request.user.is_superuser:
                    return HttpResponseRedirect(reverse('org_ext.org_list'))

            return super(OrgExtCRUDL.Choose, self).pre_process(request, *args, **kwargs)

        def get_success_url(self):
            return reverse('org_ext.org_home')

    class Home(OrgCRUDL.Home):
        pass

    class Edit(OrgCRUDL.Edit):
        pass

    class ManageAccounts(OrgCRUDL.ManageAccounts):
        pass

    class CreateLogin(OrgCRUDL.CreateLogin):
        pass

    class Join(OrgCRUDL.Join):
        pass

    class Chooser(OrgCRUDL.Chooser):
        pass

    class RefreshCache(SmartUpdateView):
        fields = ('id',)
        success_message = None
        success_url = '@org_ext.org_home'

        def pre_process(self, request, *args, **kwargs):
            cache = OrgCache(int(request.REQUEST['cache']))
            refresh_caches(self.get_object(), [cache])
            self.success_message = _("Refreshed %s cache for this organization") % cache.name