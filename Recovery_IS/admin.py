from django.contrib import admin

# Register your models here.
from .models import *
# Register your models here.

admin.site.register(RecoveryIPTrayId)
admin.site.register(RecoveryIP_RejectionGroup)
admin.site.register(RecoveryIP_Rejection_Table)
admin.site.register(RecoveryIP_Rejection_ReasonStore)
admin.site.register(RecoveryIP_Rejected_TrayScan)
admin.site.register(RecoveryIP_Accepted_TrayScan)
admin.site.register(RecoveryIP_Accepted_TrayID_Store)
admin.site.register(RecoveryIP_Rejection_Draft)
 