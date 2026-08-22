from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from modelmasterapp.models import TrayId, TrayType
from datetime import datetime

class Command(BaseCommand):
    help = 'Create trays for prefixes NR, JR, ND, JD, NL, JL, NB, JB (default 500 each). Use --force to delete matching trays first. Adds dysry for all trays.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=500, help='How many trays per prefix to create')
        parser.add_argument('--force', action='store_true', help='Delete existing trays for these prefixes before creating')

    def handle(self, *args, **options):
        prefixes = ['NR', 'JR', 'ND', 'JD', 'NL', 'JL', 'NB', 'JB']
        per_prefix = options['count']
        force = options['force']

        normal_tt = TrayType.objects.filter(tray_type__iexact='Normal').first()
        jumbo_tt = TrayType.objects.filter(tray_type__iexact='Jumbo').first()
        normal_cap = int(getattr(normal_tt, 'tray_capacity', 16) or 16)
        jumbo_cap = int(getattr(jumbo_tt, 'tray_capacity', 12) or 12)
        normal_label = normal_tt.tray_type if normal_tt else 'Normal'
        jumbo_label = jumbo_tt.tray_type if jumbo_tt else 'Jumbo'
        admin_user = get_user_model().objects.filter(is_superuser=True).first()

        if force:
            q = TrayId.objects.filter(tray_id__regex=r'^(' + '|'.join(prefixes) + r')-')
            deleted, _ = q.delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} trays for prefixes: {", ".join(prefixes)}'))

        total_created = 0
        with transaction.atomic():
            for p in prefixes:
                cap = normal_cap if p.startswith('N') else jumbo_cap
                label = normal_label if p.startswith('N') else jumbo_label
                to_create = []
                for i in range(1, per_prefix + 1):
                    tid = f"{p}-A{i:05d}"
                    if TrayId.objects.filter(tray_id=tid).exists():
                        continue
                    to_create.append(TrayId(
                        tray_id=tid,
                        tray_type=label,
                        tray_capacity=cap,
                        new_tray=True,
                        scanned=False,
                        user=admin_user,
                    ))
                if to_create:
                    TrayId.objects.bulk_create(to_create, batch_size=500)
                created = len(to_create)
                self.stdout.write(self.style.SUCCESS(f'{p}: created {created}'))
                total_created += created

        self.stdout.write(self.style.SUCCESS(f'TOTAL CREATED: {total_created}'))