from smartmin.users.views import UserCRUDL as SmartUserCRUDL
from smartmin.views import *


class UserCRUDL(SmartUserCRUDL):
    actions = ('create', 'list', 'update', 'profile', 'forget', 'recover', 'expired', 'failed', 'newpassword', 'mimic')

    class Create(SmartUserCRUDL.Create):
        fields = ('username', 'new_password', 'first_name', 'last_name', 'email')

    class Update(SmartUserCRUDL.Update):
        fields = ('username', 'new_password', 'first_name', 'last_name', 'email', 'is_active', 'last_login')

    class Profile(SmartUserCRUDL.Profile):
        fields = ('username', 'first_name', 'last_name', 'email', 'old_password', 'new_password', 'confirm_new_password')

        def pre_save(self, obj):
            obj = super(UserCRUDL.Profile, self).pre_save(obj)

            # keep our username and email in sync
            obj.username = obj.email

            return obj

        def has_permission(self, request, *args, **kwargs):
            return self.request.user.is_authenticated()
