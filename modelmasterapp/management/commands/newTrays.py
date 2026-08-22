from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

class Command(BaseCommand):
    help = "Create sequential TrayId rows like JR-A00001.. and NR-A00001.. (skips existing)"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='How many per prefix')
        parser.add_argument('--start', type=int, default=1, help='Start number')
        # include JD, ND, JL, NL in defaults
        parser.add_argument('--prefixes', nargs='+', default=['JR','NR','JD','ND','JL','NL'], help='Prefixes to generate')
        parser.add_argument('--lot-id', dest='lot_id', default=None, help='Optional lot_id to assign')
        parser.add_argument('--tray-qty', dest='tray_qty', type=int, default=None, help='Optional tray_quantity')

    def handle(self, *args, **options):
        from modelmasterapp.models import TrayId

        def fmt(prefix: str, n: int) -> str:
            # produce IDs like "JR-A00001", "NR-A00001", "JD-A00001" etc.
            return f"{prefix}-A{n:05d}"

        def generate(prefix: str, start: int, count: int, lot_id=None, tray_quantity=None):
            ids = [fmt(prefix, i) for i in range(start, start + count)]
            existing = set(TrayId.objects.filter(tray_id__in=ids).values_list('tray_id', flat=True))
            to_create = []
            now = timezone.now()
            for tid in ids:
                if tid in existing:
                    self.stdout.write(f"Skipping existing: {tid}")
                    continue
                to_create.append(TrayId(
                    tray_id=tid,
                    lot_id=lot_id,
                    tray_quantity=tray_quantity,
                    date=now
                ))
            if not to_create:
                self.stdout.write(f"No new {prefix} trays to create.")
                return 0
            with transaction.atomic():
                TrayId.objects.bulk_create(to_create)
            self.stdout.write(f"Created {len(to_create)} trays with prefix {prefix} (from {ids[0]} to {ids[-1]})")
            return len(to_create)

        total = 0
        start = options['start']
        count = options['count']
        lot_id = options['lot_id']
        tray_qty = options['tray_qty']
        prefixes = options['prefixes']

        for p in prefixes:
            total += generate(p, start, count, lot_id, tray_qty)

        self.stdout.write(self.style.SUCCESS(f"Done. Total created: {total}"))
