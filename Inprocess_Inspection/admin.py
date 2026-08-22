from django.contrib import admin
from .models import InprocessInspectionTrayCapacity

# Register your models here.

@admin.register(InprocessInspectionTrayCapacity)
class InprocessInspectionTrayCapacityAdmin(admin.ModelAdmin):
    list_display = ['tray_type', 'custom_capacity', 'is_active', 'created_at', 'created_by']
    list_filter = ['is_active', 'created_at', 'tray_type']
    search_fields = ['tray_type__tray_type']
    readonly_fields = ['created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
