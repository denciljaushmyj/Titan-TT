import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from modelmasterapp.models import ModelImage, ModelMaster


IMAGE_KEY_RE = re.compile(
    r'^(?P<model_no>\d{4})XX(?P<bath_code>[A-Z])(?P<version_code>\d{2})'
    r'(?P<view_code>RSV|LSV|FSV|TV|FV|IV|BV)?$',
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = 'Safely link ModelImage records to matching ModelMaster rows.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply links. Without this flag the command runs in dry-run mode.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Explicit dry-run mode. This is the default.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get('apply'))
        mode_label = 'APPLY' if apply_changes else 'DRY RUN'
        summary = {
            'matched': 0,
            'skipped': 0,
            'already_linked': 0,
            'errors': 0,
        }

        self.stdout.write(f'link_model_images mode: {mode_label}')

        images = ModelImage.objects.all().order_by('id')
        masters = list(ModelMaster.objects.prefetch_related('images').all())
        linked_image_ids_by_master = {
            master.id: {image.id for image in master.images.all()}
            for master in masters
        }

        for image in images:
            try:
                lookup_name = self._get_lookup_name(image)
                image_key = self._parse_image_key(lookup_name)
                if not image_key:
                    summary['skipped'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'SKIP image_id={image.id}: no valid image key in "{lookup_name}"'
                        )
                    )
                    continue

                matching_masters = [
                    master for master in masters
                    if self._master_matches_image_key(master, image_key)
                ]
                if not matching_masters:
                    summary['skipped'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'SKIP image_id={image.id} key={image_key["image_key"]}: no ModelMaster match'
                        )
                    )
                    continue

                for master in matching_masters:
                    linked_image_ids = linked_image_ids_by_master.setdefault(master.id, set())
                    if image.id in linked_image_ids:
                        summary['already_linked'] += 1
                        self.stdout.write(
                            f'ALREADY LINKED image_id={image.id} -> ModelMaster id={master.id} '
                            f'plating_stk_no={master.plating_stk_no or "-"}'
                        )
                        continue

                    summary['matched'] += 1
                    self.stdout.write(
                        f'MATCH image_id={image.id} key={image_key["image_key"]} -> '
                        f'ModelMaster id={master.id} plating_stk_no={master.plating_stk_no or "-"}'
                    )
                    if apply_changes:
                        with transaction.atomic():
                            master.images.add(image)
                        linked_image_ids.add(image.id)

            except Exception as exc:
                summary['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'ERROR image_id={getattr(image, "id", "-")}: {exc}'
                    )
                )

        self.stdout.write('')
        self.stdout.write('Summary:')
        self.stdout.write(f'Matched: {summary["matched"]}')
        self.stdout.write(f'Skipped: {summary["skipped"]}')
        self.stdout.write(f'Already linked: {summary["already_linked"]}')
        self.stdout.write(f'Errors: {summary["errors"]}')

        if apply_changes:
            self.stdout.write(self.style.SUCCESS('Completed with database links applied.'))
        else:
            self.stdout.write(self.style.WARNING('Dry run only. Re-run with --apply to link images.'))

    def _get_lookup_name(self, image):
        return (
            image.original_filename
            or os.path.basename(image.master_image.name or '')
        )

    def _parse_image_key(self, lookup_name):
        base_name = os.path.splitext(os.path.basename(lookup_name or ''))[0].upper()
        match = IMAGE_KEY_RE.match(base_name)
        if not match:
            return None

        model_no = match.group('model_no')
        bath_code = match.group('bath_code').upper()
        version_code = match.group('version_code')
        return {
            'model_no': model_no,
            'bath_code': bath_code,
            'version_code': version_code,
            'image_key': f'{model_no}xx{bath_code.lower()}{version_code}',
        }

    def _master_matches_image_key(self, master, image_key):
        return (
            self._master_fields_match(master, image_key)
            or self._plating_stock_matches(master.plating_stk_no, image_key)
        )

    def _master_fields_match(self, master, image_key):
        return (
            str(master.model_no or '').strip().upper() == image_key['model_no']
            and str(master.ep_bath_type or '').strip().upper() == image_key['bath_code']
            and str(master.version or '').strip().upper() == image_key['version_code']
        )

    def _plating_stock_matches(self, plating_stk_no, image_key):
        stock_no = str(plating_stk_no or '').strip().upper()
        if not stock_no:
            return False

        expected_pattern = (
            rf'^{re.escape(image_key["model_no"])}'
            rf'[A-Z0-9]{{2}}'
            rf'{re.escape(image_key["bath_code"])}'
            rf'{re.escape(image_key["version_code"])}$'
        )
        return re.match(expected_pattern, stock_no) is not None
