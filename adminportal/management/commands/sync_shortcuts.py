"""
Management command: sync_shortcuts
===================================
Upserts all ShortcutConfiguration records to match the canonical list
defined in the migration (0006_shortcutconfiguration.py).

Run on the server after pulling latest code:
    python manage.py sync_shortcuts

Options:
    --purge   Also deletes any DB shortcuts NOT in the canonical list
              (removes old/stale entries). Off by default.
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from adminportal.models import ShortcutConfiguration
from adminportal.services import SHORTCUT_CACHE_KEY

CANONICAL_SHORTCUTS = [
    {
        'code': 'picktable_scan',
        'keys': ['F2'],
        'key_display': 'F2',
        'label': 'Picktable Scan',
        'description': 'Activate the global tray scan flow for the current screen.',
        'action_type': 'builtin',
        'target_selector': '#globalScanBtn, #scanButton, [data-action="global-scan"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': True,
        'sort_order': 10,
        'is_active': True,
    },
    {
        'code': 'navigate_previous',
        'keys': ['ArrowUp'],
        'key_display': 'Up',
        'label': 'Previous Row',
        'description': 'Move focus to the previous visible row.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 20,
        'is_active': True,
    },
    {
        'code': 'navigate_next',
        'keys': ['ArrowDown'],
        'key_display': 'Down',
        'label': 'Next Row',
        'description': 'Move focus to the next visible row.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 21,
        'is_active': True,
    },
    {
        'code': 'scroll_left',
        'keys': ['ArrowLeft'],
        'key_display': 'Left',
        'label': 'Scroll Left',
        'description': 'Scroll the active table to the left.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 30,
        'is_active': True,
    },
    {
        'code': 'scroll_right',
        'keys': ['ArrowRight'],
        'key_display': 'Right',
        'label': 'Scroll Right',
        'description': 'Scroll the active table to the right.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 31,
        'is_active': True,
    },
    {
        'code': 'execute_pending',
        'keys': ['Enter'],
        'key_display': 'Enter',
        'label': 'Execute Action',
        'description': 'Execute the action currently attached to the focused row.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 40,
        'is_active': True,
    },
    {
        'code': 'close_active',
        'keys': ['Escape'],
        'key_display': 'Esc',
        'label': 'Close Screen',
        'description': 'Close the active popup, modal, child screen, or scan overlay.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': True,
        'sort_order': 41,
        'is_active': True,
    },
    {
        'code': 'jump_page',
        'keys': ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
        'key_display': '1-9',
        'label': 'Jump Page',
        'description': 'Jump to the matching visible page number.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 50,
        'is_active': True,
    },
    {
        'code': 'accept_row',
        'keys': ['A'],
        'key_display': 'A',
        'label': 'Accept Row',
        'description': 'Run the existing accept action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.btn-accept-is, .btn-accept, .accept-btn, [data-action="accept"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 60,
        'is_active': True,
    },
    {
        'code': 'reject_row',
        'keys': ['R'],
        'key_display': 'R',
        'label': 'Reject Row',
        'description': 'Run the existing reject action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.btn-reject-is, .btn-reject, .reject-btn, [data-action="reject"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 61,
        'is_active': True,
    },
    {
        'code': 'draft_screen',
        'keys': ['D'],
        'key_display': 'D',
        'label': 'Draft Screen',
        'description': 'Open or save the existing draft action when it is available.',
        'action_type': 'row_or_page_action',
        'target_selector': '.draft-resume-btn, .draft-btn, [data-action="draft"], [data-action="save-draft"]',
        'fallback_selector': '#saveDraftBtn, #draftBtn, .draft-save-btn, [data-action="save-draft"]',
        'contexts': ['global'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 70,
        'is_active': True,
    },
    {
        'code': 'delete_row',
        'keys': ['X'],
        'key_display': 'X',
        'label': 'Delete Row',
        'description': 'Run the existing delete action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.delete-batch-btn, .delete-row-btn, [data-action="delete"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 71,
        'is_active': True,
    },
    {
        'code': 'view_details',
        'keys': ['V'],
        'key_display': 'V',
        'label': 'View Details',
        'description': 'Open the existing detail or view action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.tray-scan-btn-DayPlanning-view, .tray-scan-btn-BQ-view, .tray-scan-btn-Jig, .jig-view-btn, .view-icon-btn, .bq-view-btn, .ba-view-btn, .view-btn, [data-action="view-details"], [data-action="view"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 80,
        'is_active': True,
    },
    {
        'code': 'tray_scan',
        'keys': ['T'],
        'key_display': 'T',
        'label': 'Tray Scan',
        'description': 'Open the existing tray scan action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.tray-scan-btn:not(.btn-reject-is):not(.btn-accept-is):not(.iqf-audit-btn), [data-action="tray-scan"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 90,
        'is_active': True,
    },
    {
        'code': 'add_jig',
        'keys': ['J', 'L'],
        'key_display': 'J/L',
        'label': 'Add Jig',
        'description': 'Open the existing add jig action.',
        'action_type': 'row_or_page_action',
        'target_selector': '.open-jig-modal-btn, .add-jig-btn, [data-action="add-jig"]',
        'fallback_selector': '#addJigBtnAlt, #addJigBtn, .add-jig-btn, [data-action="add-jig"]',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 100,
        'is_active': True,
    },
    {
        'code': 'spider_spindle',
        'keys': ['S'],
        'key_display': 'S',
        'label': 'Spider Spindle',
        'description': 'Open the existing spider spindle action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.btn-add-spider, .spider-add-btn, [data-action="add-spider"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 110,
        'is_active': True,
    },
    {
        'code': 'audit_screen',
        'keys': ['Q'],
        'key_display': 'Q',
        'label': 'Audit Screen',
        'description': 'Open the existing audit action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.iqf-audit-btn, .audit-action-btn, [data-action="iqf-audit"], [data-action="audit"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 120,
        'is_active': True,
    },
    {
        'code': 'inspection_screen',
        'keys': ['I'],
        'key_display': 'I',
        'label': 'Inspection Screen',
        'description': 'Open the existing inspection action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.ip-inspection-btn, .inspection-action-btn, [data-action="inspection"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 121,
        'is_active': True,
    },
    {
        'code': 'jig_unload',
        'keys': ['U'],
        'key_display': 'U',
        'label': 'Jig Unload',
        'description': 'Open the existing jig unload action for the selected row.',
        'action_type': 'row_action',
        'target_selector': '.z1-unload-link, .z1-unload-btn, .jig-unload-btn, [data-action="jig-unload"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 122,
        'is_active': True,
    },
    {
        'code': 'redo_screen',
        'keys': ['O'],
        'key_display': 'O',
        'label': 'Redo Screen',
        'description': 'Run the existing redo or clear-scanned-trays action when visible.',
        'action_type': 'page_action',
        'target_selector': '#trayIDRedoBtn, #trayScanRedoBtn, #rejectionTrayRedoBtn, #delinkTrayRedoBtn, #topTrayRedoBtn, .jig-redo-btn, .redo-action-btn, [data-action="redo"]',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 131,
        'is_active': True,
    },
    {
        'code': 'dp_tray_undo',
        'keys': ['O'],
        'key_display': 'O',
        'label': 'Undo Tray Clear',
        'description': 'Restore the Day Planning tray scan values cleared with C.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['/dayplanning/dp_pick_table/'],
        'allow_in_modal': True,
        'allow_when_typing': True,
        'sort_order': 132,
        'is_active': True,
    },
    {
        'code': 'dp_tray_clear',
        'keys': ['C'],
        'key_display': 'C',
        'label': 'Clear Tray Scan',
        'description': 'Clear the open Day Planning tray scan inputs.',
        'action_type': 'page_action',
        'target_selector': '#trayIDRedoBtn',
        'fallback_selector': '',
        'contexts': ['/dayplanning/dp_pick_table/'],
        'allow_in_modal': True,
        'allow_when_typing': False,
        'sort_order': 133,
        'is_active': True,
    },
    {
        'code': 'is_reject_undo',
        'keys': ['O'],
        'key_display': 'O',
        'label': 'Undo Clear',
        'description': 'Restore the Input Screening reject modal values cleared with Clear.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['/inputscreening/IS_PickTable/'],
        'allow_in_modal': True,
        'allow_when_typing': True,
        'sort_order': 134,
        'is_active': True,
    },
    {
        'code': 'is_modal_close',
        'keys': ['C'],
        'key_display': 'C',
        'label': 'Close Modal',
        'description': 'Close the open Input Screening reject modal.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['/inputscreening/IS_PickTable/'],
        'allow_in_modal': True,
        'allow_when_typing': True,
        'sort_order': 135,
        'is_active': True,
    },
    {
        'code': 'bath_number_focus',
        'keys': ['B'],
        'key_display': 'B',
        'label': 'Bath Number',
        'description': 'Focus the existing bath number selector when available.',
        'action_type': 'focus',
        'target_selector': '.bath-number-select',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 140,
        'is_active': True,
    },
    {
        'code': 'hard_refresh',
        'keys': ['Ctrl+Shift+R'],
        'key_display': 'Ctrl+Shift+R',
        'label': 'Refresh Screen',
        'description': 'Run the existing hard refresh behavior.',
        'action_type': 'builtin',
        'target_selector': '',
        'fallback_selector': '',
        'contexts': ['global'],
        'allow_in_modal': False,
        'allow_when_typing': False,
        'sort_order': 150,
        'is_active': True,
    },
]


class Command(BaseCommand):
    help = (
        "Sync ShortcutConfiguration records in the DB to match the "
        "canonical shortcut list (same as local PC). Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--purge',
            action='store_true',
            help='Also delete DB shortcuts that are NOT in the canonical list.',
        )

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped_count = 0

        canonical_codes = [s['code'] for s in CANONICAL_SHORTCUTS]

        for shortcut_data in CANONICAL_SHORTCUTS:
            code = shortcut_data['code']
            defaults = {k: v for k, v in shortcut_data.items() if k != 'code'}
            obj, created = ShortcutConfiguration.objects.update_or_create(
                code=code,
                defaults=defaults,
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  [CREATED] {code} -> {obj.key_display} ({obj.label})'))
            else:
                updated_count += 1
                self.stdout.write(f'  [UPDATED] {code} -> {obj.key_display} ({obj.label})')

        if options['purge']:
            stale = ShortcutConfiguration.objects.exclude(code__in=canonical_codes)
            stale_codes = list(stale.values_list('code', flat=True))
            deleted_count = stale.delete()[0]
            if stale_codes:
                self.stdout.write(self.style.WARNING(
                    f'  [PURGED] {deleted_count} stale shortcut(s): {stale_codes}'
                ))
            else:
                self.stdout.write('  [PURGE] No stale shortcuts found.')

        cache.delete(SHORTCUT_CACHE_KEY)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created_count}, Updated: {updated_count}'
            + (f', Purged stale: yes' if options["purge"] else '')
        ))

        # Print current DB state for confirmation
        self.stdout.write('')
        self.stdout.write('--- Current shortcuts in DB ---')
        for sc in ShortcutConfiguration.objects.order_by('sort_order'):
            status = 'ACTIVE' if sc.is_active else 'INACTIVE'
            key_display = str(sc.key_display).encode('ascii', 'replace').decode('ascii')
            label = str(sc.label).encode('ascii', 'replace').decode('ascii')
            self.stdout.write(f'  [{status}] {key_display:15s} {sc.code:25s} {label}')


