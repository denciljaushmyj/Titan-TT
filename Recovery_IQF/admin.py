from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(RecoveryIQFTrayId)
admin.site.register(RecoveryIQF_Draft_Store)


admin.site.register(RecoveryIQF_Accepted_TrayScan)
admin.site.register(RecoveryIQF_Accepted_TrayID_Store)
admin.site.register(RecoveryIQF_Rejection_ReasonStore)
admin.site.register(RecoveryIQF_Rejected_TrayScan)
admin.site.register(RecoveryIQF_Rejection_Table)
admin.site.register(RecoveryIQF_OptimalDistribution_Draft)
