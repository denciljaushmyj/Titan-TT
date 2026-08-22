from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(RecoveryBrassAuditTrayId)
admin.site.register(RecoveryBrass_Audit_Rejection_Table)
admin.site.register(RecoveryBrass_Audit_Rejection_ReasonStore)
admin.site.register(RecoveryBrass_Audit_Draft_Store)
admin.site.register(RecoveryBrass_Audit_TopTray_Draft_Store)
admin.site.register(RecoveryBrass_Audit_Rejected_TrayScan)
admin.site.register(RecoveryBrass_Audit_Accepted_TrayScan)
admin.site.register(RecoveryBrass_Audit_Accepted_TrayID_Store)

