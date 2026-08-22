from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(BrassAuditTrayId)
admin.site.register(Brass_Audit_Rejection_Table)
admin.site.register(Brass_Audit_Rejection_ReasonStore)
admin.site.register(Brass_Audit_Draft_Store)
admin.site.register(Brass_Audit_TopTray_Draft_Store)
admin.site.register(Brass_Audit_Rejected_TrayScan)
admin.site.register(Brass_Audit_Accepted_TrayScan)
admin.site.register(Brass_Audit_Accepted_TrayID_Store)


# ── AQL Sampling Plan ────────────────────────────────────────────────────────
# Single shared master table (aql_sampling_plan) — consumed by Brass Audit AND
# Nickel Audit Zone 1 / Zone 2 (Nickel_Audit/views.py, nickel_audit_zone_two/
# views.py both import AQLSamplingPlan from BrassAudit.models). Registered here
# only: Django's admin site rejects registering the same model class twice, so
# this is the one place to view/edit AQL limits for all three modules.
class AQLSamplingPlanAdmin(admin.ModelAdmin):
    list_display = ('lot_qty_from', 'lot_qty_to', 'sample_qty', 'aql_limit')
    ordering = ('lot_qty_from',)
    search_fields = ('lot_qty_from', 'lot_qty_to')


admin.site.register(AQLSamplingPlan, AQLSamplingPlanAdmin)


# ── Brass Audit Submission & Partial Lots ────────────────────────────────────

class BrassAuditSubmissionAdmin(admin.ModelAdmin):
    list_display  = ('lot_id', 'batch_id', 'submission_type', 'total_lot_qty',
                     'accepted_qty', 'rejected_qty', 'is_completed', 'created_by', 'created_at')
    list_filter   = ('submission_type', 'is_completed')
    search_fields = ('lot_id', 'batch_id')
    readonly_fields = ('created_at',)


class BrassAuditPartialAcceptAdmin(admin.ModelAdmin):
    list_display  = ('new_lot_id', 'parent_lot_id', 'parent_batch_id',
                     'accepted_qty', 'accept_trays_count', 'created_by', 'created_at')
    list_filter   = ('created_at',)
    search_fields = ('new_lot_id', 'parent_lot_id', 'parent_batch_id')
    readonly_fields = ('created_at',)


class BrassAuditPartialRejectAdmin(admin.ModelAdmin):
    list_display  = ('new_lot_id', 'parent_lot_id', 'parent_batch_id',
                     'rejected_qty', 'reject_trays_count', 'created_by', 'created_at')
    list_filter   = ('created_at',)
    search_fields = ('new_lot_id', 'parent_lot_id', 'parent_batch_id')
    readonly_fields = ('created_at',)


admin.site.register(Brass_Audit_Submission, BrassAuditSubmissionAdmin)
admin.site.register(Brass_Audit_RawSubmission)
admin.site.register(BrassAudit_PartialAcceptLot, BrassAuditPartialAcceptAdmin)
admin.site.register(BrassAudit_PartialRejectLot, BrassAuditPartialRejectAdmin)

