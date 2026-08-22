from django.contrib import admin
from .models import DPTrayId_History, DPQuickHelp

# Register your models here.

admin.site.register(DPTrayId_History)


@admin.register(DPQuickHelp)
class DPQuickHelpAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'order', 'is_active', 'created_by', 'updated_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    ordering = ('category', 'order')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'category', 'description')
        }),
        ('Display Settings', {
            'fields': ('icon_code', 'order', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at', 'created_by', 'updated_at', 'remarks'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)