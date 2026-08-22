"""
Management command to seed ModelMicroGroup table.
Wipes existing data and loads the exact 43 rows from production admin.

Usage:
    python manage.py seed_micro_groups
    python manage.py seed_micro_groups --clear-only
"""
from django.core.management.base import BaseCommand
from Jig_Loading.models import ModelMicroGroup


MICRO_GROUP_DATA = [
    # (group_name, plating_stk_no)
    ("GROUP_001", "2648YAA02/2N"),
    ("GROUP_002", "2617YAC02/2N"),
    ("GROUP_002", "2617YAD02/2N"),
    ("GROUP_003", "1805YAK02/2N"),
    ("GROUP_004", "2648WAA02"),
    ("GROUP_004", "2648WAB02"),
    ("GROUP_004", "2648WAD02"),
    ("GROUP_004", "2648WAE02"),
    ("GROUP_004", "2648WAF02"),
    ("GROUP_005", "2617WAA02"),
    ("GROUP_005", "2617WAB02"),
    ("GROUP_005", "2617WAC02"),
    ("GROUP_006", "1805WAA02"),
    ("GROUP_006", "1805WAK02"),
    ("GROUP_006", "1805WBK02"),
    ("GROUP_007", "2617SAA02"),
    ("GROUP_007", "2617SAB02"),
    ("GROUP_007", "2617SAD02"),
    ("GROUP_008", "1805SAA02"),
    ("GROUP_008", "1805SAD02"),
    ("GROUP_008", "1805SAK02"),
    ("GROUP_009", "2648SAA02"),
    ("GROUP_009", "2648SAB02"),
    ("GROUP_009", "2648SAD02"),
    ("GROUP_009", "2648SAE02"),
    ("GROUP_009", "2648SAF02"),
    ("GROUP_010", "2617NAD02"),
    ("GROUP_010", "2617NSA02"),
    ("GROUP_011", "1805QAD02/GUN"),
    ("GROUP_011", "1805QBK02/GUN"),
    ("GROUP_011", "1805QCL02/GUN"),
    ("GROUP_011", "1805QSP02/GUN"),
    ("GROUP_012", "2648QAA02/BRN"),
    ("GROUP_012", "2648QAD02/BRN"),
    ("GROUP_012", "2648QAE02/BRN"),
    ("GROUP_012", "2648QAF02/BRN"),
    ("GROUP_013", "2648QAB02/GUN"),
    ("GROUP_014", "1805NAA02"),
    ("GROUP_014", "1805NAD02"),
    ("GROUP_014", "1805NAK02"),
    ("GROUP_014", "1805NAR02"),
    ("GROUP_015", "2648NAA02"),
    ("GROUP_016", "2648KAB02/RGSS"),
]


class Command(BaseCommand):
    help = "Wipe and reseed ModelMicroGroup table with 43 exact production rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-only",
            action="store_true",
            help="Only delete all rows, do not reseed",
        )

    def handle(self, *args, **options):
        deleted, _ = ModelMicroGroup.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing rows."))

        if options["clear_only"]:
            self.stdout.write(self.style.SUCCESS("Clear-only mode. Done."))
            return

        objs = [
            ModelMicroGroup(group_name=group, plating_stk_no=psn, is_active=True)
            for group, psn in MICRO_GROUP_DATA
        ]
        ModelMicroGroup.objects.bulk_create(objs)
        self.stdout.write(self.style.SUCCESS(f"Inserted {len(objs)} rows. Total expected: 43."))

        # Verify
        total = ModelMicroGroup.objects.count()
        if total == 43:
            self.stdout.write(self.style.SUCCESS(f"✓ Verified: {total} rows in DB."))
        else:
            self.stdout.write(self.style.ERROR(f"✗ Count mismatch! Expected 43, got {total}."))
