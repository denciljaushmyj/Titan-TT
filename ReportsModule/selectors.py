"""
Read-only selectors for the Reports module.

Consolidated Report: one row per Plating Stock No showing the complete
journey (Day Planning -> ... -> Spider Spindle Z2), with every module
always shown as its own column (never collapsed to "current stage"
only). The exact same row builder is used by both the Preview API and
the Excel download so the two can never diverge.

Lineage note: Input Screening, Brass QC, IQF and Brass Audit can each
split a lot into an accepted child and/or a rejected child on PARTIAL
(and, for Brass QC / Brass Audit, on FULL_REJECT) submissions. Every
child row created this way keeps `TotalStockModel.batch_id` pointing at
the SAME batch as the parent (verified in each module's
`services/lot_service.py` `TotalStockModel.objects.create(batch_id=parent.batch_id, ...)`).
So the full lineage for a batch is simply every `TotalStockModel` row
sharing that `batch_id` — no need to walk parent/child lot_id chains
through the four separate `*_PartialAcceptLot`/`*_PartialRejectLot`
tables one hop at a time; each module's own completion flags are
checked across ALL of that batch's rows.
"""
import logging
from importlib import import_module
from datetime import datetime, time

from django.conf import settings
from django.db.models import CharField, Q, Value
from django.db.models.functions import Lower, Replace
from django.utils import timezone

logger = logging.getLogger(__name__)

PLATING_SEARCH_SEPARATORS = (' ', '-', '/', '_', '.', ':')

# Stage/column order for the consolidated journey (spec order). Zone-capable
# modules get one column per zone since a lot only ever lands in one zone.
STAGE_DAY_PLANNING = 'Day Planning'
STAGE_INPUT_SCREENING = 'Input Screening'
STAGE_BRASS_QC = 'Brass QC'
STAGE_IQF = 'IQF'
STAGE_BRASS_AUDIT = 'Brass Audit'
STAGE_JIG_LOADING = 'Jig Loading'
STAGE_IP_INSPECTION = 'IP Inspection'
STAGE_JIG_UNLOADING_Z1 = 'Jig Unloading Z1'
STAGE_JIG_UNLOADING_Z2 = 'Jig Unloading Z2'
STAGE_NICKEL_WIPING_Z1 = 'Nickel Wiping Z1'
STAGE_NICKEL_WIPING_Z2 = 'Nickel Wiping Z2'
STAGE_NICKEL_AUDIT_Z1 = 'Nickel Audit Z1'
STAGE_NICKEL_AUDIT_Z2 = 'Nickel Audit Z2'
STAGE_SS_Z1 = 'Spider Spindle Z1'
STAGE_SS_Z2 = 'Spider Spindle Z2'

MODULE_COLUMNS = [
    STAGE_DAY_PLANNING,
    STAGE_INPUT_SCREENING,
    STAGE_BRASS_QC,
    STAGE_IQF,
    STAGE_BRASS_AUDIT,
    STAGE_JIG_LOADING,
    STAGE_IP_INSPECTION,
    STAGE_JIG_UNLOADING_Z1,
    STAGE_JIG_UNLOADING_Z2,
    STAGE_NICKEL_WIPING_Z1,
    STAGE_NICKEL_WIPING_Z2,
    STAGE_NICKEL_AUDIT_Z1,
    STAGE_NICKEL_AUDIT_Z2,
    STAGE_SS_Z1,
    STAGE_SS_Z2,
]

# Field-name spec for the four early modules that can split a lot into
# accept/reject children. Every one of these lives on TotalStockModel.
_EARLY_MODULE_SPECS = [
    (STAGE_INPUT_SCREENING, dict(
        accept_flag='accepted_Ip_stock', reject_flag='rejected_ip_stock',
        few_flag='few_cases_accepted_Ip_stock', onhold_flag='ip_onhold_picking',
        out_time_field='last_process_date_time',
        accepted_qty_field='total_IP_accpeted_quantity',
        rejected_qty_field='total_qty_after_rejection_IP',
        remarks_field='IP_pick_remarks',
    )),
    (STAGE_BRASS_QC, dict(
        accept_flag='brass_qc_accptance', reject_flag='brass_qc_rejection',
        few_flag='brass_qc_few_cases_accptance', onhold_flag='brass_onhold_picking',
        out_time_field='bq_last_process_date_time',
        accepted_qty_field='brass_qc_accepted_qty',
        rejected_qty_field='brass_qc_after_rejection_qty',
        remarks_field='Bq_pick_remarks',
    )),
    (STAGE_IQF, dict(
        accept_flag='iqf_acceptance', reject_flag='iqf_rejection',
        few_flag='iqf_few_cases_acceptance', onhold_flag='iqf_onhold_picking',
        out_time_field='iqf_last_process_date_time',
        accepted_qty_field='iqf_accepted_qty',
        rejected_qty_field='iqf_after_rejection_qty',
        remarks_field='IQF_pick_remarks',
    )),
    (STAGE_BRASS_AUDIT, dict(
        accept_flag='brass_audit_accptance', reject_flag='brass_audit_rejection',
        few_flag='brass_audit_few_cases_accptance', onhold_flag='brass_audit_onhold_picking',
        out_time_field='brass_audit_last_process_date_time',
        accepted_qty_field='brass_audit_accepted_qty',
        rejected_qty_field=None,  # no dedicated field; derived from lot_qty - accepted
        remarks_field='BA_pick_remarks',
    )),
]

DT_FORMAT = '%d-%b-%Y %I:%M %p'


def _fmt(dt):
    if not dt:
        return ''
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime(DT_FORMAT)


def _normalize_unload_lot_id(value):
    """Same normalization the Jig Unloading report uses."""
    value = str(value or '').strip().lstrip('-')
    if ':' in value:
        value = value.rsplit(':', 1)[-1].strip()
    if value.startswith('JLOT-') and '-' in value[5:]:
        value = value.rsplit('-', 1)[-1]
    return value


def _first_remark(*values):
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ''


def _module_cell(status, in_time=None, out_time=None, lot_qty=None, accepted_qty=None,
                  rejected_qty=None, user=None, remarks=None):
    """Format one module's cell — the same multi-line block for Preview and Excel."""
    if status == 'Not Reached':
        return 'IN : --\nOUT: --\nStatus : Not Reached'
    lines = [f"IN : {_fmt(in_time)}", f"OUT: {_fmt(out_time)}"]
    if lot_qty is not None:
        lines.append(f"Lot Qty : {lot_qty}")
    if accepted_qty is not None:
        lines.append(f"Accepted : {accepted_qty}")
    if rejected_qty is not None:
        lines.append(f"Rejected : {rejected_qty}")
    lines.append(f"Status : {status}")
    if user:
        lines.append(f"User : {user}")
    if remarks:
        lines.append(f"Remarks : {remarks}")
    return '\n'.join(lines)


def _early_module_status(stock, spec):
    """Return (status, out_time) for one of the four split-capable modules,
    or (None, None) if this row was never processed at that module."""
    if getattr(stock, spec['reject_flag'], False):
        return 'Rejected', getattr(stock, spec['out_time_field'], None)
    if getattr(stock, spec['accept_flag'], False):
        return 'Accepted', getattr(stock, spec['out_time_field'], None)
    few = getattr(stock, spec['few_flag'], False)
    onhold = getattr(stock, spec['onhold_flag'], False)
    if few and not onhold:
        return 'Partially Accepted', getattr(stock, spec['out_time_field'], None)
    if few and onhold:
        return 'In Progress', getattr(stock, spec['out_time_field'], None)
    return None, None


def _pick_early_module_row(stocks_for_batch, spec):
    """Among every TotalStockModel row for this batch (root + every split
    child), find the one carrying this module's own completion flags.
    Prefers the latest out-time if more than one row matches."""
    best = None
    for stock in stocks_for_batch:
        status, out_time = _early_module_status(stock, spec)
        if status is None:
            continue
        if best is None or (out_time and (not best[2] or out_time > best[2])):
            best = (stock, status, out_time)
    return best


def _early_module_cells(stocks_for_batch, prev_out_time):
    """Build cells for Input Screening / Brass QC / IQF / Brass Audit, in
    order, threading each reached stage's out-time forward as the next
    stage's in-time. Returns (cells, statuses, last_out_time)."""
    cells = {}
    statuses = {}
    running_out = prev_out_time
    for name, spec in _EARLY_MODULE_SPECS:
        match = _pick_early_module_row(stocks_for_batch, spec)
        if not match:
            cells[name] = _module_cell('Not Reached')
            statuses[name] = None
            continue
        stock, status, out_time = match
        lot_qty = int(stock.total_stock or 0)
        accepted_qty = getattr(stock, spec['accepted_qty_field'], None)
        rejected_qty_field = spec['rejected_qty_field']
        if rejected_qty_field:
            rejected_qty = getattr(stock, rejected_qty_field, None)
        elif status == 'Rejected':
            rejected_qty = lot_qty - int(accepted_qty or 0)
        else:
            rejected_qty = None
        cells[name] = _module_cell(
            status,
            in_time=running_out,
            out_time=out_time,
            lot_qty=lot_qty,
            accepted_qty=accepted_qty,
            rejected_qty=rejected_qty,
            remarks=getattr(stock, spec['remarks_field'], None),
        )
        statuses[name] = status
        running_out = out_time or running_out
    return cells, statuses, running_out


def _jig_loading_cells(jig_record, prev_out_time):
    """Returns (jig_loading_cell, ip_inspection_cell, last_out_time)."""
    if not jig_record:
        return _module_cell('Not Reached'), _module_cell('Not Reached'), prev_out_time

    jig_out = jig_record.IP_loaded_date_time or jig_record.updated_at
    jig_cell = _module_cell(
        'Completed',
        in_time=prev_out_time,
        out_time=jig_out,
        lot_qty=jig_record.original_lot_qty or jig_record.updated_lot_qty,
        accepted_qty=jig_record.loaded_cases_qty,
        user=jig_record.user.username if getattr(jig_record, 'user_id', None) else None,
        remarks=_first_remark(jig_record.pick_remarks, jig_record.remarks),
    )
    if jig_record.jig_position:
        ip_cell = _module_cell(
            'Completed',
            in_time=jig_out,
            out_time=jig_record.updated_at,
            remarks=jig_record.remarks,
        )
        return jig_cell, ip_cell, jig_record.updated_at
    return jig_cell, _module_cell('Not Reached'), jig_out


def _late_module_cells(unload_record, zone_map, prev_out_time):
    """Build cells for Jig Unloading / Nickel Wiping / Nickel Audit / Spider
    Spindle, each split into Z1/Z2 columns. Returns (cells, statuses,
    last_out_time) covering all 8 zone columns."""
    zone_columns = [
        STAGE_JIG_UNLOADING_Z1, STAGE_JIG_UNLOADING_Z2,
        STAGE_NICKEL_WIPING_Z1, STAGE_NICKEL_WIPING_Z2,
        STAGE_NICKEL_AUDIT_Z1, STAGE_NICKEL_AUDIT_Z2,
        STAGE_SS_Z1, STAGE_SS_Z2,
    ]
    cells = {name: _module_cell('Not Reached') for name in zone_columns}
    statuses = {name: None for name in zone_columns}
    if not unload_record:
        return cells, statuses, prev_out_time

    zone = zone_map.get(unload_record.plating_color_id)
    running_out = prev_out_time

    # Jig Unloading itself uses generic (non nq_*/na_* prefixed) fields —
    # Zone 1/2 is still the same JigUnloadAfterTable row, routed by the
    # lot's Plating_Color allow-list, same as Nickel Wiping/Audit below.
    ju_status = 'Accepted' if unload_record.unload_accepted else (
        'Completed' if unload_record.Un_loaded_date_time else 'Pending'
    )
    ju_remarks = (
        f"Missing qty: {unload_record.unload_missing_qty}"
        if unload_record.unload_missing_qty else ''
    )
    ju_cell = _module_cell(
        ju_status,
        in_time=unload_record.created_at,
        out_time=unload_record.Un_loaded_date_time,
        lot_qty=unload_record.total_case_qty,
        accepted_qty=unload_record.accepted_qty,
        remarks=ju_remarks,
    )
    ju_out = unload_record.Un_loaded_date_time or unload_record.created_at
    if zone == 'z1':
        cells[STAGE_JIG_UNLOADING_Z1] = ju_cell
        statuses[STAGE_JIG_UNLOADING_Z1] = ju_status
    elif zone == 'z2':
        cells[STAGE_JIG_UNLOADING_Z2] = ju_cell
        statuses[STAGE_JIG_UNLOADING_Z2] = ju_status
    running_out = ju_out or running_out

    # Nickel Wiping
    nq_out = ju_out
    if (unload_record.nq_qc_accptance or unload_record.nq_qc_rejection
            or (unload_record.nq_qc_few_cases_accptance and not unload_record.nq_onhold_picking)):
        nq_status = (
            'Rejected' if unload_record.nq_qc_rejection
            else 'Accepted' if unload_record.nq_qc_accptance
            else 'Partially Accepted'
        )
        nq_cell = _module_cell(
            nq_status,
            in_time=ju_out,
            out_time=unload_record.nq_last_process_date_time,
            lot_qty=unload_record.total_case_qty,
            accepted_qty=unload_record.nq_qc_accepted_qty,
            rejected_qty=unload_record.nq_missing_qty or None,
            remarks=unload_record.nq_pick_remarks,
        )
        nq_out = unload_record.nq_last_process_date_time or ju_out
        if zone == 'z1':
            cells[STAGE_NICKEL_WIPING_Z1] = nq_cell
            statuses[STAGE_NICKEL_WIPING_Z1] = nq_status
        elif zone == 'z2':
            cells[STAGE_NICKEL_WIPING_Z2] = nq_cell
            statuses[STAGE_NICKEL_WIPING_Z2] = nq_status
        running_out = nq_out or running_out

    # Nickel Audit
    na_out = nq_out
    if (unload_record.na_qc_accptance or unload_record.na_qc_rejection
            or (unload_record.na_qc_few_cases_accptance and not unload_record.na_onhold_picking)):
        na_status = (
            'Rejected' if unload_record.na_qc_rejection
            else 'Accepted' if unload_record.na_qc_accptance
            else 'Partially Accepted'
        )
        na_cell = _module_cell(
            na_status,
            in_time=nq_out,
            out_time=unload_record.na_last_process_date_time,
            lot_qty=unload_record.total_case_qty,
            accepted_qty=unload_record.na_qc_accepted_qty,
            rejected_qty=unload_record.na_missing_qty or None,
            remarks=unload_record.na_pick_remarks,
        )
        na_out = unload_record.na_last_process_date_time or nq_out
        if zone == 'z1':
            cells[STAGE_NICKEL_AUDIT_Z1] = na_cell
            statuses[STAGE_NICKEL_AUDIT_Z1] = na_status
        elif zone == 'z2':
            cells[STAGE_NICKEL_AUDIT_Z2] = na_cell
            statuses[STAGE_NICKEL_AUDIT_Z2] = na_status
        running_out = na_out or running_out

    # Spider Spindle — independent zone-completion flags, not tied to the
    # plating-color zone used above.
    if getattr(unload_record, 'ss_z1_completed', False):
        cells[STAGE_SS_Z1] = _module_cell(
            'Completed',
            in_time=na_out,
            out_time=unload_record.ss_z1_completed_at,
            user=(unload_record.ss_z1_completed_by.username
                  if unload_record.ss_z1_completed_by_id else None),
            remarks=unload_record.spider_pick_remarks,
        )
        statuses[STAGE_SS_Z1] = 'Completed'
        running_out = unload_record.ss_z1_completed_at or running_out
    if getattr(unload_record, 'ss_z2_completed', False):
        cells[STAGE_SS_Z2] = _module_cell(
            'Completed',
            in_time=na_out,
            out_time=unload_record.ss_z2_completed_at,
            user=(unload_record.ss_z2_completed_by.username
                  if unload_record.ss_z2_completed_by_id else None),
            remarks=unload_record.spider_pick_remarks,
        )
        statuses[STAGE_SS_Z2] = 'Completed'
        running_out = unload_record.ss_z2_completed_at or running_out

    return cells, statuses, running_out


def get_consolidated_report_rows(date_from=None, date_to=None, plating_stock_no=''):
    """
    Build the consolidated journey rows. One row per Plating Stock No, using
    the batch with the most recent stage activity. Every module column is
    always populated — either with its actual data or "Not Reached" — so the
    report shows the complete lifecycle rather than only the latest stage.

    date_from / date_to filter on the latest stage activity timestamp.
    plating_stock_no is a partial (icontains) match.
    """
    from modelmasterapp.models import TotalStockModel, Plating_Color
    from Jig_Loading.models import JigCompleted
    from Jig_Unloading.models import JigUnloadAfterTable

    stock_qs = TotalStockModel.objects.filter(
        batch_id__isnull=False,
        batch_id__total_batch_quantity__gt=0,
        remove_lot=False,
    ).select_related('batch_id').order_by('-created_at')

    if plating_stock_no:
        stock_qs = stock_qs.filter(
            batch_id__plating_stk_no__icontains=plating_stock_no.strip()
        )

    stocks = list(stock_qs)
    lot_ids = {s.lot_id for s in stocks if s.lot_id}
    batch_ids = {s.batch_id_id for s in stocks if s.batch_id_id}

    # Every TotalStockModel row sharing a batch_id (root + every accept/reject
    # child ever created at Input Screening/Brass QC/IQF/Brass Audit) — needed
    # to follow lot splits instead of getting stuck on whichever single row
    # was picked as "most recently active."
    # Exclude synthetic EX-* excess-lot rows: Jig Loading creates its own
    # TotalStockModel row for leftover/excess quantity (sharing the same
    # batch_id), but it never actually goes through Input Screening/Brass
    # QC/IQF/Brass Audit itself — including it here can let its own stale
    # completion flags (and a coincidentally later timestamp) get picked
    # over the real lot's row, showing e.g. the excess row's tiny qty
    # instead of the genuine lot's qty for an early-stage cell.
    stocks_by_batch = {}
    if batch_ids:
        for s in TotalStockModel.objects.filter(
            batch_id_id__in=batch_ids
        ).exclude(lot_id__startswith='EX-'):
            stocks_by_batch.setdefault(s.batch_id_id, []).append(s)

    # Bulk maps — avoid N+1
    jig_by_lot = {}
    for record in JigCompleted.objects.filter(
        draft_status='submitted'
    ).order_by('updated_at').only(
        'lot_id', 'jig_position', 'updated_at', 'pick_remarks',
        'remarks', 'unloading_remarks', 'multi_model_allocation',
        'IP_loaded_date_time', 'original_lot_qty', 'updated_lot_qty',
        'loaded_cases_qty', 'user',
    ):
        keys = {record.lot_id}
        for allocation in record.multi_model_allocation or []:
            if isinstance(allocation, dict) and allocation.get('lot_id'):
                keys.add(str(allocation['lot_id']))
        for key in keys:
            if key in lot_ids:
                jig_by_lot[key] = record  # latest submitted wins

    unload_by_lot = {}
    for record in JigUnloadAfterTable.objects.all().order_by('Un_loaded_date_time'):
        keys = {_normalize_unload_lot_id(record.lot_id)}
        for combined in record.combine_lot_ids or []:
            keys.add(_normalize_unload_lot_id(combined))
        for key in keys:
            if key in lot_ids:
                unload_by_lot[key] = record

    # Zone lookup for Jig Unloading / Nickel Wiping / Nickel Audit: same
    # table, routed to Zone 1 or Zone 2 by the lot's Plating_Color flags.
    zone_map = {}
    for pc in Plating_Color.objects.all().only('id', 'jig_unload_zone_1', 'jig_unload_zone_2'):
        if pc.jig_unload_zone_1:
            zone_map[pc.id] = 'z1'
        elif pc.jig_unload_zone_2:
            zone_map[pc.id] = 'z2'

    tz_aware = timezone.is_aware(timezone.now())

    def to_dt(d, end=False):
        dt = datetime.combine(d, time.max if end else time.min)
        return timezone.make_aware(dt) if tz_aware else dt

    from_dt = to_dt(date_from) if date_from else None
    to_dt_val = to_dt(date_to, end=True) if date_to else None

    best_by_stk = {}
    for stock in stocks:
        batch = stock.batch_id
        stk_no = (batch.plating_stk_no or '').strip()
        if not stk_no:
            continue

        jig_record = jig_by_lot.get(stock.lot_id)
        unload_record = unload_by_lot.get(stock.lot_id)
        stocks_for_batch = stocks_by_batch.get(stock.batch_id_id) or [stock]

        dp_reached = bool(batch.Moved_to_D_Picker or stock.tray_scan_status)
        dp_out = batch.date_time or stock.created_at
        dp_cell = _module_cell(
            'Completed',
            in_time=dp_out,
            out_time=dp_out,
            lot_qty=batch.total_batch_quantity,
            remarks=batch.dp_pick_remarks,
        ) if dp_reached else _module_cell('Not Reached')

        early_cells, early_statuses, running_out = _early_module_cells(
            stocks_for_batch, dp_out if dp_reached else stock.created_at
        )
        jig_cell, ip_cell, running_out = _jig_loading_cells(jig_record, running_out)
        late_cells, late_statuses, running_out = _late_module_cells(
            unload_record, zone_map, running_out
        )

        modules = {STAGE_DAY_PLANNING: dp_cell}
        modules.update(early_cells)
        modules[STAGE_JIG_LOADING] = jig_cell
        modules[STAGE_IP_INSPECTION] = ip_cell
        modules.update(late_cells)

        activity = running_out or stock.created_at

        # Date-range filter on latest stage activity
        if from_dt and (not activity or activity < from_dt):
            continue
        if to_dt_val and activity and activity > to_dt_val:
            continue

        remarks = _first_remark(
            getattr(unload_record, 'spider_pick_remarks', None) if unload_record else None,
            getattr(unload_record, 'na_pick_remarks', None) if unload_record else None,
            getattr(unload_record, 'nq_pick_remarks', None) if unload_record else None,
            getattr(jig_record, 'unloading_remarks', None) if jig_record else None,
            getattr(jig_record, 'pick_remarks', None) if jig_record else None,
            getattr(jig_record, 'remarks', None) if jig_record else None,
            stock.BA_pick_remarks, stock.IQF_pick_remarks,
            stock.Bq_pick_remarks, stock.IP_pick_remarks,
            batch.dp_pick_remarks,
        )

        row = {
            'plating_stk_no': stk_no,
            'lot_qty': int(stock.total_stock or batch.total_batch_quantity or 0),
            'modules': modules,
            'remarks': remarks,
            '_activity': activity,
        }

        existing = best_by_stk.get(stk_no)
        if (
            existing is None
            or (row['_activity'] and not existing['_activity'])
            or (row['_activity'] and existing['_activity']
                and row['_activity'] > existing['_activity'])
        ):
            best_by_stk[stk_no] = row

    sentinel = datetime.min
    if tz_aware:
        sentinel = timezone.make_aware(datetime(1, 1, 2))
    rows = sorted(
        best_by_stk.values(),
        key=lambda r: r['_activity'] or sentinel,
        reverse=True,
    )
    for idx, row in enumerate(rows, start=1):
        row['s_no'] = idx
        row.pop('_activity', None)
    return rows


def _normalize_plating_search(value):
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


def _plating_search_key_expression():
    expression = Lower('plating_stk_no')
    for separator in PLATING_SEARCH_SEPARATORS:
        expression = Replace(
            expression,
            Value(separator),
            Value(''),
            output_field=CharField(),
        )
    return expression


def _rank_plating_matches(values, query, limit):
    q_lower = query.lower()
    normalized_query = _normalize_plating_search(query)

    def sort_key(value):
        value_lower = value.lower()
        normalized_value = _normalize_plating_search(value)
        return (
            not value_lower.startswith(q_lower),
            not (normalized_query and normalized_value.startswith(normalized_query)),
            value_lower,
        )

    return sorted({value for value in values if value}, key=sort_key)[:limit]


def search_plating_stock(query, limit=15):
    """
    Autocomplete for Plating Stock No. Uses Elasticsearch when configured
    (settings.ELASTICSEARCH_URL + elasticsearch package installed),
    otherwise falls back to an indexed DB partial match.
    """
    from modelmasterapp.models import ModelMasterCreation

    query = (query or '').strip()
    if not query:
        return []

    results = set()
    es_url = getattr(settings, 'ELASTICSEARCH_URL', None)
    if es_url:
        try:
            Elasticsearch = import_module('elasticsearch').Elasticsearch
            client = Elasticsearch(es_url, request_timeout=2)
            response = client.search(
                index=getattr(settings, 'ELASTICSEARCH_PLATING_INDEX', 'plating_stock'),
                query={
                    'bool': {
                        'should': [
                            {'match_phrase_prefix': {'plating_stk_no': query}},
                            {'wildcard': {
                                'plating_stk_no.keyword': {
                                    'value': f'*{query}*',
                                    'case_insensitive': True,
                                },
                            }},
                            {'wildcard': {
                                'plating_stk_no': {
                                    'value': f'*{query}*',
                                    'case_insensitive': True,
                                },
                            }},
                        ],
                        'minimum_should_match': 1,
                    },
                },
                size=limit,
            )
            hits = [
                hit['_source'].get('plating_stk_no')
                for hit in response.get('hits', {}).get('hits', [])
            ]
            results.update(h for h in hits if h)
        except Exception:
            logger.warning('Elasticsearch autocomplete failed; using DB fallback', exc_info=True)

    # DB fallback: union of batch stock numbers (ModelMasterCreation, the
    # source the consolidated report uses) and the ModelMaster catalogue,
    # so every known plating stock number is suggested while typing.
    from modelmasterapp.models import ModelMaster

    normalized_query = _normalize_plating_search(query)

    def _matches(model):
        queryset = model.objects.exclude(
            plating_stk_no__isnull=True
        ).exclude(
            plating_stk_no=''
        ).annotate(
            _plating_search_key=_plating_search_key_expression()
        )
        filters = Q(plating_stk_no__icontains=query)
        if normalized_query:
            filters |= Q(_plating_search_key__contains=normalized_query)
        return queryset.filter(filters).values_list('plating_stk_no', flat=True).distinct()

    results.update(_matches(ModelMasterCreation))
    results.update(_matches(ModelMaster))
    # prefix matches first, including punctuation-insensitive prefixes, then alphabetical
    return _rank_plating_matches(results, query, limit)
