from django.core.management.base import BaseCommand
from Recovery_DP.models import RecoveryTrayId

class Command(BaseCommand):
    help = 'Load NB and JB trays into DB'

    def handle(self, *args, **kwargs):
        nb_trays = [
            RecoveryTrayId(tray_id=f"NB-A{str(i).zfill(5)}", tray_type="Normal", tray_capacity=16)
            for i in range(1, 200)
        ]
        jb_trays = [
            RecoveryTrayId(tray_id=f"JB-A{str(i).zfill(5)}", tray_type="Jumbo", tray_capacity=12)
            for i in range(1, 200)
        ]
        RecoveryTrayId.objects.bulk_create(nb_trays + jb_trays)
        self.stdout.write(self.style.SUCCESS('Successfully loaded all trays'))
