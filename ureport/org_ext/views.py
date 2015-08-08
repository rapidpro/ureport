from __future__ import absolute_import, unicode_literals


from dash.orgs.models import Org
from dash.orgs.views import OrgCRUDL, InferOrgMixin, OrgPermsMixin, SmartUpdateView
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

from smartmin.views import SmartCRUDL


class OrgExtCRUDL(SmartCRUDL):
    actions = ('create', 'list', 'update', 'choose', 'home', 'edit',
               'manage_accounts', 'create_login', 'join', 'chooser')
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

