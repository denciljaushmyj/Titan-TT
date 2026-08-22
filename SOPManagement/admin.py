from django.contrib import admin

from .models import SOPMaster, SOPModule


@admin.register(SOPModule)
class SOPModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    search_fields = ('name',)


@admin.register(SOPMaster)
class SOPMasterAdmin(admin.ModelAdmin):
    list_display = ('sop_title', 'module', 'version', 'is_active', 'is_deleted', 'uploaded_by', 'uploaded_date')
    list_filter = ('module', 'is_active', 'is_deleted')
    search_fields = ('sop_title', 'version')
    readonly_fields = ('uploaded_date', 'updated_at', 'file_size')
