from django.contrib import admin
from models import DashBlock, DashBlockType

class DashBlockTypeAdmin(admin.ModelAdmin):
    list_display = ('slug', 'created_on', 'created_by')
    ordering = ('-created_on',)

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

admin.site.register(DashBlockType, DashBlockTypeAdmin)

class DashBlockAdmin(admin.ModelAdmin):
    list_display = ('title', 'dashblock_type', 'is_active', 'priority', 'created_on', 'created_by')
    list_filter = ('is_active', 'dashblock_type')
    ordering = ('-is_active', 'dashblock_type', '-priority')

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

admin.site.register(DashBlock, DashBlockAdmin)
