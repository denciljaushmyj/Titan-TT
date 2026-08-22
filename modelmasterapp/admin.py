from django.contrib import admin
from .models import *
#test
class ModelMasterAdmin(admin.ModelAdmin):
    list_display = ['model_no', 'brand', 'ep_bath_type', 'tray_type_display', 'tray_code', 'tray_capacity_display', 'plating_stk_no']
    search_fields = ['model_no', 'brand', 'plating_stk_no', 'tray_code']
    list_filter = ['brand', 'ep_bath_type', 'tray_code']

    def tray_type_display(self, obj):
        if obj.tray_type:
            return obj.tray_type.tray_type
        return ''
    tray_type_display.short_description = 'Tray Type'
    tray_type_display.admin_order_field = 'tray_type__tray_type'

    def tray_capacity_display(self, obj):
        # prefer explicit ModelMaster.tray_capacity, else fallback to linked TrayType
        if obj.tray_capacity:
            return obj.tray_capacity
        if obj.tray_type and getattr(obj.tray_type, 'tray_capacity', None) is not None:
            return obj.tray_type.tray_capacity
        return ''
    tray_capacity_display.short_description = 'Tray Capacity'
    tray_capacity_display.admin_order_field = 'tray_capacity'

admin.site.register(ModelMaster, ModelMasterAdmin)
admin.site.register(PolishFinishType)
admin.site.register(TrayType)
admin.site.register(Vendor)


@admin.register(ModelVersionComparison)
class ModelVersionComparisonAdmin(admin.ModelAdmin):
    list_display = (
        "model_number",
        "version",
        "o_ring_pocket",
        "thickness",
        "title",
        "is_active",
        "updated_at",
    )

    search_fields = (
        "model_number",
        "version",
        "title",
    )

    list_filter = (
        "version",
        "is_active",
    )


@admin.register(ModelVersionComparisonImage)
class ModelVersionComparisonImageAdmin(admin.ModelAdmin):
    list_display = (
        "comparison",
        "original_filename",
        "display_order",
        "uploaded_at",
    )

    search_fields = (
        "comparison__model_number",
        "comparison__version",
        "original_filename",
    )

class ModelMasterCreationAdmin(admin.ModelAdmin):
    list_display = ['batch_id', 'lot_id', 'model_stock_no', 'upload_type', 'total_batch_quantity', 'Moved_to_D_Picker', 'date_time']
    list_filter = ['upload_type', 'Moved_to_D_Picker']
    search_fields = ['batch_id', 'lot_id', 'plating_stk_no']

admin.site.register(ModelMasterCreation, ModelMasterCreationAdmin)
admin.site.register(Version)
admin.site.register(Location)
admin.site.register(Category)
admin.site.register(TrayId)
admin.site.register(DraftTrayId)

admin.site.register(ModelImage)
admin.site.register(Plating_Color)
admin.site.register(TotalStockModel)
admin.site.register(DP_TrayIdRescan)

admin.site.register(TrayAutoSaveData)
admin.site.register(LookLikeModel)


# ── Universal Lot Hierarchy ──────────────────────────────────────────────────

class LotTraySnapshotInline(admin.TabularInline):
    model = LotTraySnapshot
    extra = 0
    readonly_fields = ('tray_id', 'tray_qty', 'tray_order', 'top_tray', 'tray_status', 'created_at')
    ordering = ('tray_order',)
    can_delete = False
    fk_name = 'lot'


class LotMasterAdmin(admin.ModelAdmin):
    list_display  = ('lot_id', 'parent_lot_id', 'root_lot_id', 'module_name',
                     'source_module', 'submission_type', 'total_qty', 'status', 'active',
                     'created_by', 'created_at')
    list_filter   = ('module_name', 'source_module', 'submission_type', 'status', 'active')
    search_fields = ('lot_id', 'parent_lot_id', 'root_lot_id')
    readonly_fields = ('created_at',)
    inlines       = [LotTraySnapshotInline]


class LotTraySnapshotAdmin(admin.ModelAdmin):
    list_display  = ('tray_id', 'tray_qty', 'tray_order', 'top_tray',
                     'tray_status', 'lot', 'created_at')
    list_filter   = ('tray_status', 'top_tray')
    search_fields = ('tray_id', 'lot__lot_id')
    readonly_fields = ('created_at',)
    ordering      = ('lot', 'tray_order')


admin.site.register(LotMaster, LotMasterAdmin)
admin.site.register(LotTraySnapshot, LotTraySnapshotAdmin)
