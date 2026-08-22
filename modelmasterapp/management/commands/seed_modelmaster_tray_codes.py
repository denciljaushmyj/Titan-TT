from django.core.management.base import BaseCommand
from django.db import transaction

from modelmasterapp.models import ModelMaster
from modelmasterapp.tray_code_mapping import TRAY_CODE_MASTER_DATA


class Command(BaseCommand):
    help = 'Seed only ModelMaster.tray_code from tray-code master data without changing any other fields.'

    def handle(self, *args, **options):
        updated = []
        unchanged = []
        missing = []

        with transaction.atomic():
            for plating_stk_no, tray_info in TRAY_CODE_MASTER_DATA.items():
                tray_codes = tray_info.get('tray_codes') or []
                if not tray_codes:
                    continue

                tray_code = tray_codes[0]
                model_master = ModelMaster.objects.filter(plating_stk_no=plating_stk_no).first()
                if not model_master:
                    missing.append(plating_stk_no)
                    continue

                if model_master.tray_code == tray_code:
                    unchanged.append(plating_stk_no)
                    continue

                old_code = model_master.tray_code or ''
                model_master.tray_code = tray_code
                model_master.save(update_fields=['tray_code'])
                updated.append((plating_stk_no, old_code, tray_code))

        for plating_stk_no, old_code, tray_code in updated:
            self.stdout.write(f'Updated {plating_stk_no}: {old_code or "<blank>"} -> {tray_code}')

        if missing:
            self.stdout.write(self.style.WARNING(f'Missing ModelMaster rows: {", ".join(missing)}'))

        self.stdout.write(self.style.SUCCESS(
            f'Tray-code seed complete. Updated={len(updated)}, unchanged={len(unchanged)}, missing={len(missing)}'
        ))