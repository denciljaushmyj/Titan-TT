"""Read helpers for Jig Loading pick-table workflows."""

import re
from dataclasses import dataclass

from .models import Jig, JigCompleted, JigLoadingManualDraft


def get_ip_info_remarks_by_psn(psn_list):
    """Resolve the shared IP Info remark for each plating_stk_no (PSN).

    The remark is a property of the PSN, not of an individual lot: any
    submitted Jig Loading record — or, failing that, any Inprocess Inspection
    record that has completed (jig_position set) — carrying a remark for a
    given PSN applies to every lot sharing that PSN, regardless of qty or
    processing stage. Both cases live on the same JigCompleted.remarks field,
    resolved here in a single bulk query (no per-row N+1).
    """
    psns = {str(p).strip() for p in (psn_list or []) if str(p or '').strip()}
    if not psns:
        return {}

    rows = (
        JigCompleted.objects.filter(plating_stock_num__in=psns)
        .exclude(remarks__isnull=True)
        .exclude(remarks='')
        .order_by('-updated_at')
        .values('plating_stock_num', 'remarks', 'draft_status', 'jig_position')
    )

    submitted_map = {}
    completed_map = {}
    for row in rows:
        psn = row['plating_stock_num']
        if row['draft_status'] == 'submitted' and psn not in submitted_map:
            submitted_map[psn] = row['remarks']
        if row['jig_position'] and psn not in completed_map:
            completed_map[psn] = row['remarks']

    return {psn: submitted_map.get(psn) or completed_map.get(psn) or '' for psn in psns}


TRAY_VALUE_KEYS = {
    'tray_id',
    'trayid',
    'tray',
    'scanned_tray_id',
    'scannedtrayid',
    'actual_tray_id',
    'delink_tray_id',
    'old_tray_id',
    'new_tray_id',
    'value',
}

JIG_ID_PATTERN = re.compile(r'^J\d{3}-\d{4}$')


@dataclass(frozen=True)
class JigDraftLookup:
    jig_id: str
    lot_id: str
    batch_id: str
    source: str


def normalize_tray_id(value):
    return ''.join(str(value or '').split()).upper()


def normalize_jig_id(value):
    normalized = ''.join(str(value or '').split()).upper()
    if normalized.startswith('J!'):
        normalized = 'J1' + normalized[2:]
    return normalized


def looks_like_jig_id(value):
    return bool(JIG_ID_PATTERN.match(normalize_jig_id(value)))


def payload_contains_tray_id(payload, normalized_tray_id):
    if not normalized_tray_id:
        return False

    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = str(key or '').replace('-', '_').lower()
            compact_key = key_name.replace('_', '')
            if key_name in TRAY_VALUE_KEYS or compact_key in TRAY_VALUE_KEYS:
                if normalize_tray_id(value) == normalized_tray_id:
                    return True
            if isinstance(value, (dict, list)) and payload_contains_tray_id(value, normalized_tray_id):
                return True
        return False

    if isinstance(payload, list):
        return any(payload_contains_tray_id(item, normalized_tray_id) for item in payload)

    return normalize_tray_id(payload) == normalized_tray_id


def draft_contains_tray_id(draft, normalized_tray_id):
    return any(
        payload_contains_tray_id(payload, normalized_tray_id)
        for payload in (
            draft.scanned_trays,
            draft.delink_tray_info,
            draft.half_filled_tray_info,
            draft.multi_model_allocation,
            draft.draft_data,
        )
    )


def find_active_draft_by_scanned_tray(tray_id, user=None):
    normalized_tray_id = normalize_tray_id(tray_id)
    if len(normalized_tray_id) < 6:
        return None

    queryset = JigLoadingManualDraft.objects.filter(draft_status='active').order_by('-updated_at')
    if user is not None:
        if not getattr(user, 'is_authenticated', False):
            return None
        queryset = queryset.filter(user=user)

    queryset = queryset.only(
        'lot_id',
        'batch_id',
        'scanned_trays',
        'delink_tray_info',
        'half_filled_tray_info',
        'multi_model_allocation',
        'draft_data',
        'updated_at',
    )

    for draft in queryset:
        if draft_contains_tray_id(draft, normalized_tray_id):
            return draft
    return None


def find_active_draft_by_jig_id(jig_id, user=None):
    normalized_jig_id = normalize_jig_id(jig_id)
    if not looks_like_jig_id(normalized_jig_id):
        return None

    if user is not None and not getattr(user, 'is_authenticated', False):
        return None

    completed_qs = JigCompleted.objects.filter(
        jig_id__iexact=normalized_jig_id,
        draft_status__in=['draft', 'active'],
    ).order_by('-updated_at')
    if user is not None:
        completed_qs = completed_qs.filter(user=user)

    completed_draft = completed_qs.only(
        'jig_id',
        'lot_id',
        'batch_id',
        'draft_status',
        'updated_at',
    ).first()
    if completed_draft and completed_draft.lot_id:
        return completed_draft

    manual_qs = JigLoadingManualDraft.objects.filter(
        jig_id__iexact=normalized_jig_id,
        draft_status='active',
    ).order_by('-updated_at')
    if user is not None:
        manual_qs = manual_qs.filter(user=user)

    manual_draft = manual_qs.only(
        'jig_id',
        'lot_id',
        'batch_id',
        'draft_status',
        'updated_at',
    ).first()
    if manual_draft and manual_draft.lot_id:
        return manual_draft

    jig = Jig.objects.filter(
        jig_qr_id__iexact=normalized_jig_id,
        drafted=True,
    ).only(
        'jig_qr_id',
        'lot_id',
        'batch_id',
        'current_user_id',
    ).first()

    if not jig or not jig.lot_id:
        return None
    if user is not None and jig.current_user_id and jig.current_user_id != user.id:
        return None

    return JigDraftLookup(
        jig_id=normalized_jig_id,
        lot_id=str(jig.lot_id or ''),
        batch_id=str(jig.batch_id or ''),
        source='Jig',
    )