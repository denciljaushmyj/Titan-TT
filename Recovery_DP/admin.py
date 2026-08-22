from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(RecoveryLocation)
admin.site.register(RecoveryMasterCreation)
admin.site.register(RecoveryTrayId)
admin.site.register(RecoveryDraftTrayId)
admin.site.register(RecoveryStockModel)
admin.site.register(RecoveryTrayId_History)

