from .models import *
from smartmin.views import *
from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from django.utils.translation import ugettext_lazy as _

class DashBlockCRUDL(SmartCRUDL):
    model = DashBlock
    permissions = True
    actions = ('create', 'update', 'list')

    class Add(OrgPermsMixin, SmartCreateView):
        grant_permissions = ('dashblocks.change_dashblock',)

        def get_context_data(self, *args, **kwargs):
            context = super(DashBlockCRUDL.Add, self).get_context_data(*args, **kwargs)
            context['type'] = self.get_type()
            return context

        def derive_title(self):
            block_type = self.get_type()
            if block_type:
                return "Create %s" % block_type.name
            else:
                return "Create Content Block"

        def derive_exclude(self):
            exclude = super(DashBlockCRUDL.Add, self).derive_exclude()


            if not self.request.user.is_superuser:
                exclude.append('org')

            block_type = self.get_type()
            if block_type:
                exclude.append('dashblock_type')

                if not block_type.has_summary:
                    exclude.append('summary')

                if not block_type.has_video:
                    exclude.append('video_id')

                if not block_type.has_title:
                    exclude.append('title')

                if not block_type.has_tags:
                    exclude.append('tags')

                if not block_type.has_image:
                    exclude.append('image')

                if not block_type.has_link:
                    exclude.append('link')

                if not block_type.has_color:
                    exclude.append('color')

            return exclude

        def derive_initial(self, *args, **kwargs):
            initial = super(DashBlockCRUDL.Add, self).derive_initial(*args, **kwargs)
            dashblock_type = self.get_type()
            org = self.derive_org()
            other_blocks = DashBlock.objects.filter(is_active=True, org=org, dashblock_type=dashblock_type).order_by('-priority')
            if not other_blocks:
                initial['priority'] = 0
            else:
                initial['priority'] = other_blocks[0].priority + 1
            return initial

        def pre_save(self, obj):
            obj = super(DashBlockCRUDL.Add, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            block_type = self.get_type()
            if block_type:
                obj.dashblock_type = block_type

            obj.space_tags()
            return obj

    class SlugBlock(OrgPermsMixin, SmartListView):
        fields = ('title', 'priority', 'dashblock_type', 'tags')
        link_fields = ('title',)
        default_order = '-priority'
        search_fields = ('title__icontains', 'content__icontains', 'summary__icontains')
        title = "Content Blocks"
        add_button = True

        def derive_exclude(self):
            exclude = super(DashBlockCRUDL.SlugBlock, self).derive_exclude()

            block_type = self.get_type()
            if block_type:
                if not block_type.has_tags:
                    exclude.append('tags')

            return exclude

        def get_type(self):
            if 'type' in self.request.REQUEST and not self.request.REQUEST.get('type') == '0':
                return DashBlockType.objects.get(id=self.request.REQUEST.get('type'))
            elif 'slug' in self.request.REQUEST:
                return DashBlockType.objects.get(slug=self.request.REQUEST.get('slug'))
            return None

        def get_queryset(self, **kwargs):
            queryset = super(DashBlockCRUDL.SlugBlock, self).get_queryset(**kwargs)

            queryset = queryset.filter(org=self.derive_org())

            dashblock_type = self.get_type()

            if dashblock_type:
                queryset = queryset.filter(dashblock_type=dashblock_type)

            queryset = queryset.filter(dashblock_type__is_active=True)

            return queryset

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('title', 'priority', 'org', 'dashblock_type', 'tags')
            return self.fields

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('title', 'summary', 'content', 'image', 'color', 'link', 'video_id', 'dashblock_type', 'priority', 'is_active')

        def pre_save(self, obj):
            obj = super(DashBlockCRUDL.Update, self).pre_save(obj)
            obj.space_tags()
            return obj

        def get_success_url(self):
            return "%s?type=%d" % (reverse('dashblocks.dashblock_list'), self.object.dashblock_type.id)

        def derive_exclude(self):
            exclude = super(DashBlockCRUDL.Update, self).derive_exclude()

            block_type = self.object.dashblock_type

            if not block_type.has_summary:
                exclude.append('summary')

            if not block_type.has_video:
                exclude.append('video_id')

            if not block_type.has_title:
                exclude.append('title')

            if not block_type.has_tags:
                exclude.append('tags')

            if not block_type.has_image:
                exclude.append('image')

            if not block_type.has_link:
                exclude.append('link')

            if not block_type.has_color:
                exclude.append('color')
                
            if not self.request.user.has_perm(self.permission):
                exclude.append('dashblock_type')


            return exclude

        def get_context_data(self, *args, **kwargs):
            context = super(DashBlockCRUDL.Update, self).get_context_data(*args, **kwargs)
            context['type'] = self.object.dashblock_type
            return context

        def derive_title(self):
            return "Edit %s" % self.object.dashblock_type.name

    class Create(OrgPermsMixin, SmartCreateView):
        grant_permissions = ('dashblocks.change_dashblock',)

        def get_success_url(self):
            return "%s?type=%d" % (reverse('dashblocks.dashblock_list'), self.object.dashblock_type.id)

        def derive_exclude(self):
            exclude = super(DashBlockCRUDL.Create, self).derive_exclude()

            block_type = self.get_type()
            if block_type:
                exclude.append('dashblock_type')

                if not block_type.has_summary:
                    exclude.append('summary')

                if not block_type.has_video:
                    exclude.append('video_id')

                if not block_type.has_title:
                    exclude.append('title')

                if not block_type.has_tags:
                    exclude.append('tags')

                if not block_type.has_image:
                    exclude.append('image')

                if not block_type.has_link:
                    exclude.append('link')

                if not block_type.has_color:
                    exclude.append('color')

            # if this user does not have global permissins, remove org as a field
            if not self.request.user.has_perm(self.permission):
                exclude.append('org')

            return exclude

        def derive_initial(self, *args, **kwargs):
            initial = super(DashBlockCRUDL.Create, self).derive_initial(*args, **kwargs)
            dashblock_type = self.get_type()
            other_blocks = DashBlock.objects.filter(is_active=True, dashblock_type=dashblock_type).order_by('-priority')
            if not other_blocks:
                initial['priority'] = 0
            else:
                initial['priority'] = other_blocks[0].priority + 1
            return initial

        def derive_title(self):
            block_type = self.get_type()
            if block_type:
                return "Create %s" % block_type.name
            else:
                return "Create Content Block"

        def get_type(self):
            if 'type' in self.request.REQUEST:
                return DashBlockType.objects.get(id=self.request.REQUEST.get('type'))
            return None

        def get_context_data(self, *args, **kwargs):
            context = super(DashBlockCRUDL.Create, self).get_context_data(*args, **kwargs)
            context['type'] = self.get_type()
            return context

        def pre_save(self, obj):
            obj = super(DashBlockCRUDL.Create, self).pre_save(obj)

            block_type = self.get_type()
            if block_type:
                obj.dashblock_type = block_type

            # if the user doesn't have global permissions, set the org appropriately
            if not self.request.user.has_perm(self.permission):
                obj.org = self.request.org
            
            obj.space_tags()
            return obj
            
    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'priority', 'dashblock_type', 'tags')
        link_fields = ('title',)
        default_order = '-modified_on'
        search_fields = ('title__icontains', 'content__icontains', 'summary__icontains')
        title = "Content Blocks"

        def derive_exclude(self):
            exclude = super(DashBlockCRUDL.List, self).derive_exclude()

            block_type = self.get_type()
            if block_type:
                if not block_type.has_tags:
                    exclude.append('tags')

            return exclude

        def derive_title(self):
            type = self.get_type()
            if not type:
                return _("Content Blocks")
            else:
                return _("%s Blocks") % type.name

        def get_type(self):
            if 'type' in self.request.REQUEST and not self.request.REQUEST.get('type') == '0':
                return DashBlockType.objects.get(id=self.request.REQUEST.get('type'))
            elif 'slug' in self.request.REQUEST:
                return DashBlockType.objects.get(slug=self.request.REQUEST.get('slug'))
            return None

        def get_queryset(self, **kwargs):
            queryset = super(DashBlockCRUDL.List, self).get_queryset(**kwargs)

            dashblock_type = self.get_type()
            if dashblock_type:
                queryset = queryset.filter(dashblock_type=dashblock_type)

            queryset = queryset.filter(dashblock_type__is_active=True)

            # if this user doesn't have global dashblock privileges, filter by their organization
            if not self.request.user.is_superuser:
                queryset = queryset.filter(org=self.request.org)

            return queryset

        def get_context_data(self, *args, **kwargs):
            context = super(DashBlockCRUDL.List, self).get_context_data(*args, **kwargs)
            context['types'] = DashBlockType.objects.filter(is_active=True)
            context['filtered_type'] = self.get_type()
            return context


class DashBlockTypeCRUDL(SmartCRUDL):
    model = DashBlockType
    actions = ('create', 'update', 'list')

    class List(SmartListView):
        title = "Content Types"
        fields = ('name', 'slug', 'description')
        link_fields = ('name',)

class DashBlockImageCRUDL(SmartCRUDL):
    model = DashBlockImage
    actions = ('create', 'update', 'list')

    class Update(SmartUpdateView):
        exclude = ('dashblock', 'modified_by', 'modified_on', 'created_on', 'created_by', 'width', 'height')
        title = "Edit Image"
        success_message = "Image edited successfully."        

        def get_success_url(self):
            return reverse('dashblocks.dashblock_update', args=[self.object.dashblock.id])

    class Create(SmartCreateView):
        exclude = ('dashblock', 'is_active', 'modified_by', 'modified_on', 'created_on', 'created_by', 'width', 'height')
        title = "Add Image"
        success_message = "Image added successfully."

        def derive_initial(self, *args, **kwargs):
            initial = super(DashBlockImageCRUDL.Create, self).derive_initial(*args, **kwargs)
            dashblock = DashBlock.objects.get(pk=self.request.REQUEST.get('dashblock'))
            images = dashblock.sorted_images()
            if not images:
                initial['priority'] = 0
            else:
                initial['priority'] = images[0].priority + 1
            return initial

        def get_success_url(self):
            return reverse('dashblocks.dashblock_update', args=[self.object.dashblock.id])

        def pre_save(self, obj):
            obj = super(DashBlockImageCRUDL.Create, self).pre_save(obj)
            obj.dashblock = DashBlock.objects.get(pk=self.request.REQUEST.get('dashblock'))
            return obj
