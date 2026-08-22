from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(RecoveryBrassTrayId)
admin.site.register(RecoveryBrass_QC_Rejection_Table)
admin.site.register(RecoveryBrass_QC_Rejection_ReasonStore)
admin.site.register(RecoveryBrass_QC_Rejected_TrayScan)
admin.site.register(RecoveryBrass_Qc_Accepted_TrayScan)
admin.site.register(RecoveryBrass_Qc_Accepted_TrayID_Store)
admin.site.register(RecoveryBrass_QC_Draft_Store)
admin.site.register(RecoveryBrass_TopTray_Draft_Store)

  