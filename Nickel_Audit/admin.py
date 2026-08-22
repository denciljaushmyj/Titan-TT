from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(Nickel_AuditTrayId)
admin.site.register(Nickel_Audit_Rejection_Table)
admin.site.register(Nickel_Audit_Rejection_ReasonStore)
admin.site.register(Nickel_Audit_Draft_Store)
admin.site.register(Nickel_Audit_TopTray_Draft_Store)
admin.site.register(Nickel_Audit_Rejected_TrayScan)
admin.site.register(Nickel_Audit_Accepted_TrayScan)
admin.site.register(Nickel_Audit_Accepted_TrayID_Store)


# ── AQL Sampling Plan ────────────────────────────────────────────────────────
# Proxy of BrassAudit.AQLSamplingPlan (same shared aql_sampling_plan table,
# same limits Brass Audit uses) — registered here so Nickel Audit's own admin
# section also shows/edits the AQL limits, not just Brass Audit's.
class NickelAuditAQLSamplingPlanAdmin(admin.ModelAdmin):
    list_display = ('lot_qty_from', 'lot_qty_to', 'sample_qty', 'aql_limit')
    ordering = ('lot_qty_from',)
    search_fields = ('lot_qty_from', 'lot_qty_to')


admin.site.register(NickelAudit_AQLSamplingPlan, NickelAuditAQLSamplingPlanAdmin)

