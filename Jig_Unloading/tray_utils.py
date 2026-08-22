"""
Shared utility for fetching tray data from upstream tables when no tray records
exist in the current stage (NickelQcTrayId, JigUnload_TrayId, etc.).

Used by: Nickel Inspection (Z1/Z2), Nickel Audit (Z1/Z2) PickTrayIdList views.
"""
import logging
import re

from django.db.models import Q

logger = logging.getLogger(__name__)


TRAY_ID_FORMAT_PATTERN = re.compile(r'^[A-Z]+-A\d{5}$')


def normalize_jig_unload_tray_id(raw_tray_id):
    return str(raw_tray_id or '').strip().upper()


def normalize_combine_lot_id(combined):
    """Normalise a JigUnloadAfterTable.combine_lot_ids entry to its plain source lot_id.

    Zone 1 stores plain lot_ids (e.g. 'LID210820252112300004') while Zone 2 stores
    prefixed variants (e.g. 'JLOT-8CEDE491A4A3-LID210820252112300004' or
    'JLOT-8CEDE491A4A3:LID210820252112300004'). Without normalising both formats to
    the same plain lot_id, the same source lot submitted from both zones is treated
    as two unrelated lots instead of being merged into a single combined lot.
    """
    if not combined:
        return combined
    s = str(combined).strip().lstrip('-')
    if ':' in s:
        possible_lot = s.rsplit(':', 1)[-1].strip()
        if possible_lot:
            return possible_lot
    if s.startswith('JLOT-') and '-' in s[5:]:
        return s.rsplit('-', 1)[1]
    return s


def is_valid_jig_unload_tray_id_format(raw_tray_id):
    return bool(TRAY_ID_FORMAT_PATTERN.match(normalize_jig_unload_tray_id(raw_tray_id)))


def _tray_id_variants(raw_tray_id):
    tray_id = normalize_jig_unload_tray_id(raw_tray_id)
    if not tray_id:
        return set()

    variants = {tray_id}
    match = re.match(r'^([A-Z]+)-A(\d+)$', tray_id)
    if match:
        prefix, digits = match.groups()
        if len(digits) <= 5:
            variants.add(f'{prefix}-A{digits.zfill(5)}')
    return variants


def _lot_id_aliases(raw_lot_id):
    value = str(raw_lot_id or '').strip()
    if not value:
        return set()

    aliases = {value}
    if ':' in value:
        aliases.add(value.rsplit(':', 1)[-1].strip())
    if value.startswith('JLOT-') and '-' in value[5:]:
        aliases.add(value.rsplit('-', 1)[-1].strip())
    return {alias for alias in aliases if alias}


def _allowed_lot_aliases(allowed_lot_ids):
    aliases = set()
    for lot_id in allowed_lot_ids or []:
        aliases.update(_lot_id_aliases(lot_id))
    return aliases


def _iter_payload_dicts(payload):
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            if isinstance(value, (dict, list)):
                yield from _iter_payload_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                yield from _iter_payload_dicts(item)


def _payload_contains_tray_id(payload, tray_variants):
    for entry in _iter_payload_dicts(payload):
        entry_tray_id = entry.get('tray_id') or entry.get('trayId')
        if not entry_tray_id:
            continue
        entry_tray_id = normalize_jig_unload_tray_id(entry_tray_id)
        if not is_valid_jig_unload_tray_id_format(entry_tray_id):
            continue
        if _tray_id_variants(entry_tray_id) & tray_variants:
            return True
    return False


def _collect_lot_aliases_from_payload(payload):
    aliases = set()
    scalar_keys = ('lot_id', 'main_lot_id', 'source_lot_id', 'primary_lot_id')
    list_keys = ('combined_lot_ids', 'source_lot_ids')

    for entry in _iter_payload_dicts(payload):
        for key in scalar_keys:
            aliases.update(_lot_id_aliases(entry.get(key)))
        for key in list_keys:
            value = entry.get(key)
            if isinstance(value, list):
                for lot_id in value:
                    aliases.update(_lot_id_aliases(lot_id))
    return aliases


def _variant_query(field_name, tray_variants):
    query = Q()
    for tray_id in tray_variants:
        query |= Q(**{f'{field_name}__iexact': tray_id})
    return query


def _make_tray_conflict(tray_id, source, linked_lot='', record_id=None):
    linked_lot_text = linked_lot or 'another lot'
    return {
        'occupied': True,
        'tray_id': tray_id,
        'source': source,
        'linked_lot': linked_lot,
        'record_id': record_id,
        'message': (
            f'Tray "{tray_id}" is already reserved for {linked_lot_text} in {source}. '
            'Please use a free tray or release/delink the existing tray first.'
        ),
    }


def _has_allowed_lot(record_lot_aliases, allowed_aliases):
    return bool(record_lot_aliases and allowed_aliases and record_lot_aliases & allowed_aliases)


def find_jig_unload_tray_conflict(raw_tray_id, allowed_lot_ids=None, include_tray_master=False):
    """Return a conflict dict when a tray is reserved by another active lot.

    Jig Unloading keeps in-progress tray scans in JSON-backed draft/autosave
    records before final submit. Those records must reserve tray IDs just like
    final tray rows, otherwise the same physical tray can be scanned into a
    second lot while the first lot is still pending submission.
    """
    tray_id = normalize_jig_unload_tray_id(raw_tray_id)
    tray_variants = _tray_id_variants(tray_id)
    if not tray_variants:
        return None

    allowed_aliases = _allowed_lot_aliases(allowed_lot_ids)

    from modelmasterapp.models import TrayId
    from Jig_Unloading.models import JigUnload_TrayId, JigUnloadDraft, JigUnloadAutoSave, JUSubmittedZ1

    if include_tray_master:
        for tray in TrayId.objects.filter(_variant_query('tray_id', tray_variants)).only(
            'id', 'tray_id', 'lot_id', 'scanned', 'delink_tray'
        ):
            if tray.delink_tray:
                continue
            record_lots = _lot_id_aliases(tray.lot_id)
            if _has_allowed_lot(record_lots, allowed_aliases):
                continue
            if tray.scanned or record_lots:
                return _make_tray_conflict(
                    tray_id,
                    'Tray master',
                    next(iter(record_lots), ''),
                    tray.id,
                )

    for tray in JigUnload_TrayId.objects.filter(_variant_query('tray_id', tray_variants)).only(
        'id', 'tray_id', 'lot_id', 'delink_tray'
    ):
        if tray.delink_tray:
            continue
        record_lots = _lot_id_aliases(tray.lot_id)
        if _has_allowed_lot(record_lots, allowed_aliases):
            continue
        return _make_tray_conflict(
            tray_id,
            'Jig Unloading submitted trays',
            next(iter(record_lots), ''),
            tray.id,
        )

    submitted_rows = JUSubmittedZ1.objects.exclude(tray_data__isnull=True).only(
        'id', 'jig_completed_id', 'lot_id', 'tray_data', 'is_draft'
    )
    for submitted in submitted_rows.iterator():
        if not _payload_contains_tray_id(submitted.tray_data, tray_variants):
            continue
        record_lots = _lot_id_aliases(submitted.lot_id)
        record_lots.update(_collect_lot_aliases_from_payload(submitted.tray_data))
        if _has_allowed_lot(record_lots, allowed_aliases):
            continue
        source = 'Jig Unloading draft/model save' if submitted.is_draft else 'Jig Unloading model save'
        return _make_tray_conflict(tray_id, source, next(iter(record_lots), ''), submitted.id)

    draft_rows = JigUnloadDraft.objects.exclude(draft_data__isnull=True).only(
        'draft_id', 'main_lot_id', 'combined_lot_ids', 'draft_data'
    )
    for draft in draft_rows.iterator():
        if not _payload_contains_tray_id(draft.draft_data, tray_variants):
            continue
        record_lots = _lot_id_aliases(draft.main_lot_id)
        for combined_lot_id in draft.combined_lot_ids or []:
            record_lots.update(_lot_id_aliases(combined_lot_id))
        record_lots.update(_collect_lot_aliases_from_payload(draft.draft_data))
        if _has_allowed_lot(record_lots, allowed_aliases):
            continue
        return _make_tray_conflict(
            tray_id,
            'Jig Unloading draft',
            next(iter(record_lots), ''),
            draft.draft_id,
        )

    autosave_rows = JigUnloadAutoSave.objects.exclude(tray_data__isnull=True).only(
        'id', 'main_lot_id', 'combined_lot_ids', 'tray_data', 'updated_at'
    )
    for autosave in autosave_rows.iterator():
        if autosave.is_expired() or not autosave.has_meaningful_data():
            continue
        if not _payload_contains_tray_id(autosave.tray_data, tray_variants):
            continue
        record_lots = _lot_id_aliases(autosave.main_lot_id)
        for combined_lot_id in autosave.combined_lot_ids or []:
            record_lots.update(_lot_id_aliases(combined_lot_id))
        record_lots.update(_collect_lot_aliases_from_payload(autosave.tray_data))
        if _has_allowed_lot(record_lots, allowed_aliases):
            continue
        return _make_tray_conflict(
            tray_id,
            'Jig Unloading autosave',
            next(iter(record_lots), ''),
            autosave.id,
        )

    return None


def get_model_master_tray_info(plating_stk_no, fallback_type='', fallback_cap=0):
    """
    Dynamically look up tray type code from ModelMaster by plating stock number.
    Returns (tray_type_str, tray_capacity_int).
    Falls back to provided defaults if lookup fails.
    """
    if plating_stk_no:
        from modelmasterapp.models import ModelMaster
        mm = ModelMaster.objects.select_related('tray_type').filter(
            plating_stk_no=plating_stk_no
        ).first()
        if mm and mm.tray_type:
            return mm.tray_type.tray_type, mm.tray_capacity or fallback_cap
    return fallback_type, fallback_cap


def get_upstream_tray_distribution(lot_id):
    """
    When no tray records exist in the current-stage tables, look up the
    JigUnloadAfterTable for combine_lot_ids, then fetch REAL tray IDs from
    the nearest upstream table that has data.

    Quantities are redistributed to match JigUnloadAfterTable.total_case_qty.

    Returns:
        (list[dict], str) — (tray_data_list, tray_source) on success
        (None, None)      — when no upstream data is available
    """
    from Jig_Unloading.models import JigUnloadAfterTable, JigUnload_TrayId, JUSubmittedZ1
    from BrassAudit.models import BrassAuditTrayId, Brass_Audit_Accepted_TrayID_Store
    from Brass_QC.models import BrassTrayId
    from Jig_Loading.models import JigLoadTrayId

    # 1. Get JigUnloadAfterTable record for this UNLOT lot_id
    juat = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
    if not juat:
        return None, None

    combine_lot_ids = juat.combine_lot_ids or []
    if not combine_lot_ids:
        return None, None

    total_qty = juat.total_case_qty or 0
    tray_capacity = juat.tray_capacity or 16

    if total_qty <= 0:
        return None, None

    # 2. Try JigUnload_TrayId with combine_lot_ids first
    for lid in combine_lot_ids:
        trays = JigUnload_TrayId.objects.filter(lot_id=lid).order_by('id')
        if trays.exists():
            data = []
            for idx, t in enumerate(trays, 1):
                data.append({
                    's_no': idx,
                    'tray_id': t.tray_id,
                    'tray_quantity': t.tray_qty or 0,
                    'top_tray': t.top_tray,
                    'delink_tray': t.delink_tray,
                    'rejected_tray': t.rejected_tray,
                })
            logger.info(
                "[upstream_tray] Found %d trays in JigUnload_TrayId for %s (via %s)",
                len(data), lot_id, lid,
            )
            return data, "JigUnload_TrayId (via combine_lot_ids)"

    # 2b. Try JUSubmittedZ1.tray_data (Zone 1 Jig Unloading stores tray scans here)
    for lid in combine_lot_ids:
        ju_sub = JUSubmittedZ1.objects.filter(lot_id=lid, is_draft=False).order_by('-submitted_at').first()
        if ju_sub and ju_sub.tray_data:
            data = []
            for idx, t in enumerate(ju_sub.tray_data, 1):
                tray_id = t.get('tray_id', '')
                if not tray_id:
                    continue
                data.append({
                    's_no': idx,
                    'tray_id': tray_id,
                    'tray_quantity': t.get('qty', t.get('tray_qty', 0)) or 0,
                    'top_tray': t.get('is_top_tray', False),
                    'delink_tray': False,
                    'rejected_tray': False,
                })
            if data:
                logger.info(
                    "[upstream_tray] Found %d trays in JUSubmittedZ1 for %s (via %s)",
                    len(data), lot_id, lid,
                )
                print(f"✅ Found {len(data)} trays from JUSubmittedZ1 (via combine_lot_ids)")
                return data, "JUSubmittedZ1 (via combine_lot_ids)"

    # 3. Search upstream tables for REAL tray IDs
    #    Priority: closest upstream stage → farthest
    upstream_sources = [
        (BrassAuditTrayId, 'tray_quantity', "BrassAuditTrayId"),
        (Brass_Audit_Accepted_TrayID_Store, 'tray_qty', "Brass_Audit_Accepted_TrayID_Store"),
        (BrassTrayId, 'tray_quantity', "BrassTrayId"),
        (JigLoadTrayId, None, "JigLoadTrayId"),  # JigLoadTrayId may not have qty
    ]

    upstream_trays = []
    tray_source = None

    for SourceModel, qty_field, source_name in upstream_sources:
        for lid in combine_lot_ids:
            trays = SourceModel.objects.filter(lot_id=lid).order_by('id')
            if trays.exists():
                upstream_trays = list(trays)
                tray_source = source_name
                break
        if upstream_trays:
            break

    if not upstream_trays:
        logger.warning(
            "[upstream_tray] No upstream tray data for %s (combine_lot_ids=%s)",
            lot_id, combine_lot_ids,
        )
        return None, None

    # 4. Extract real tray IDs (prefer non-rejected, non-delinked)
    active_tray_ids = []
    top_tray_id = None

    for t in upstream_trays:
        is_rejected = getattr(t, 'rejected_tray', False)
        is_delinked = getattr(t, 'delink_tray', False)
        is_top = getattr(t, 'top_tray', False)

        if is_rejected or is_delinked:
            continue

        if is_top:
            top_tray_id = t.tray_id
        else:
            active_tray_ids.append(t.tray_id)

    # If all trays were filtered out, use all of them
    if not active_tray_ids and not top_tray_id:
        for t in upstream_trays:
            is_top = getattr(t, 'top_tray', False)
            if is_top:
                top_tray_id = t.tray_id
            else:
                active_tray_ids.append(t.tray_id)

    # 5. Redistribute quantities based on total_case_qty & tray_capacity
    num_full = total_qty // tray_capacity
    remainder = total_qty % tray_capacity
    num_trays_needed = num_full + (1 if remainder > 0 else 0)

    # Build ordered list of tray IDs: top tray first, then full trays
    ordered_ids = []
    if remainder > 0 and top_tray_id:
        ordered_ids.append(top_tray_id)
    elif remainder > 0 and active_tray_ids:
        # Use first active tray as top if no dedicated top tray
        ordered_ids.append(active_tray_ids.pop(0))

    ordered_ids.extend(active_tray_ids)

    data = []
    for i in range(num_trays_needed):
        if i >= len(ordered_ids):
            break  # Don't fabricate tray IDs

        if remainder > 0 and i == 0:
            qty = remainder
            is_top = True
        else:
            qty = tray_capacity
            is_top = False

        data.append({
            's_no': i + 1,
            'tray_id': ordered_ids[i],
            'tray_quantity': qty,
            'top_tray': is_top,
            'delink_tray': False,
            'rejected_tray': False,
        })

    logger.info(
        "[upstream_tray] Built %d trays from %s for %s (total_qty=%d, cap=%d)",
        len(data), tray_source, lot_id, total_qty, tray_capacity,
    )
    return data, f"upstream ({tray_source})"
