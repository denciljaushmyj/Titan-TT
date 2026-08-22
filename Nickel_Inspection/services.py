def _nq_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tray_id(value):
    return str(value or '').strip().upper()


def _tray_sort_key(tray_id):
    return _tray_id(tray_id)


def _row_get(row, key, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _clean_tray_rows(rows, qty_keys=('qty', 'tray_quantity')):
    clean_rows = []
    for index, row in enumerate(rows or []):
        tray_id = _tray_id(_row_get(row, 'tray_id', ''))
        qty = 0
        for key in qty_keys:
            qty = _nq_int(_row_get(row, key, 0))
            if qty:
                break
        if not tray_id or qty <= 0:
            continue
        clean_rows.append({
            'tray_id': tray_id,
            'qty': qty,
            'is_top': bool(_row_get(row, 'is_top', False) or _row_get(row, 'top_tray', False)),
            '_index': index,
        })
    return clean_rows


def _mark_top_by_smallest_qty(rows):
    if not rows:
        return []
    top_index = min(
        range(len(rows)),
        key=lambda index: (rows[index]['qty'], _tray_sort_key(rows[index]['tray_id']), rows[index].get('_index', index)),
    )
    normalized = []
    for index, row in enumerate(rows):
        item = {
            'tray_id': row['tray_id'],
            'qty': row['qty'],
            'is_top': index == top_index,
        }
        item['top_tray'] = item['is_top']
        normalized.append(item)
    return sorted(normalized, key=lambda row: (not row['is_top'], _tray_sort_key(row['tray_id'])))


def build_reject_slots(rejected_qty, reject_capacity):
    rejected_qty = _nq_int(rejected_qty)
    reject_capacity = max(_nq_int(reject_capacity), 1)
    quantities = []
    remaining_qty = rejected_qty
    while remaining_qty > 0:
        slot_qty = min(remaining_qty, reject_capacity)
        quantities.append(slot_qty)
        remaining_qty -= slot_qty

    sorted_quantities = sorted(enumerate(quantities), key=lambda item: (item[1], item[0]))
    return [
        {
            'qty': qty,
            'is_top': index == 0,
            'slot_no': index + 1,
        }
        for index, (_, qty) in enumerate(sorted_quantities)
    ]


def build_nq_rejection_allocation(original_trays, rejected_qty, reject_capacity):
    original_rows = _clean_tray_rows(original_trays)
    rejected_qty = _nq_int(rejected_qty)
    remaining_reject_qty = rejected_qty
    delink_slots = []
    accept_auto_trays = []

    for row in original_rows:
        if remaining_reject_qty <= 0:
            accept_auto_trays.append({'tray_id': row['tray_id'], 'qty': row['qty']})
        elif row['qty'] <= remaining_reject_qty:
            delink_slots.append({
                'tray_id': row['tray_id'],
                'qty': row['qty'],
                'is_required': True,
            })
            remaining_reject_qty -= row['qty']
        else:
            accept_auto_trays.append({
                'tray_id': row['tray_id'],
                'qty': row['qty'] - remaining_reject_qty,
            })
            remaining_reject_qty = 0

    accept_auto_trays = _mark_top_by_smallest_qty(accept_auto_trays)
    accept_slots = [
        {
            'qty': row['qty'],
            'is_top': row['is_top'],
            'slot_no': index + 1,
        }
        for index, row in enumerate(accept_auto_trays)
    ]

    return {
        'reject_slots': build_reject_slots(rejected_qty, reject_capacity),
        'delink_slots': delink_slots,
        'auto_delink_tray_ids': [row['tray_id'] for row in delink_slots],
        'accept_auto_trays': accept_auto_trays,
        'accept_slots': accept_slots,
    }


def normalize_reject_trays(reject_trays, expected_slots):
    rows = _clean_tray_rows(reject_trays)
    expected_qtys = [slot['qty'] for slot in expected_slots or []]
    if len(rows) != len(expected_qtys):
        raise ValueError('Scan all reject tray slots before submitting.')

    seen_trays = set()
    for row in rows:
        if row['tray_id'] in seen_trays:
            raise ValueError(f"Duplicate reject tray {row['tray_id']} scanned.")
        seen_trays.add(row['tray_id'])

    rows = sorted(rows, key=lambda row: (row['qty'], row['_index']))
    if [row['qty'] for row in rows] != expected_qtys:
        raise ValueError('Reject tray quantities do not match backend allocation.')

    normalized = []
    for index, row in enumerate(rows):
        item = {
            'tray_id': row['tray_id'],
            'qty': row['qty'],
            'is_top': index == 0,
            'slot_no': index + 1,
        }
        item['top_tray'] = item['is_top']
        normalized.append(item)
    return normalized


def normalize_delink_trays(delink_trays, expected_delink_slots):
    expected_slots = expected_delink_slots or []
    expected_ids = [_tray_id(slot.get('tray_id')) for slot in expected_slots]
    expected_id_set = set(expected_ids)

    submitted_ids = []
    for row in delink_trays or []:
        tray_id = _tray_id(row.get('tray_id') if isinstance(row, dict) else row)
        if tray_id:
            submitted_ids.append(tray_id)

    if not expected_ids:
        if submitted_ids:
            raise ValueError('No delink trays are required for this rejection.')
        return []

    submitted_id_set = set(submitted_ids)
    if len(submitted_ids) != len(submitted_id_set):
        raise ValueError('Duplicate delink tray scanned.')

    if submitted_id_set != expected_id_set:
        missing_ids = [tray_id for tray_id in expected_ids if tray_id not in submitted_id_set]
        extra_ids = [tray_id for tray_id in submitted_ids if tray_id not in expected_id_set]
        details = []
        if missing_ids:
            details.append('missing ' + ', '.join(missing_ids))
        if extra_ids:
            details.append('unexpected ' + ', '.join(extra_ids))
        raise ValueError('Scan/tap all required delink trays: ' + '; '.join(details))

    return [
        {
            'tray_id': slot['tray_id'],
            'qty': slot['qty'],
            'is_delinked': True,
            'slot_no': index + 1,
        }
        for index, slot in enumerate(expected_slots)
    ]


def normalize_operator_delink_trays(delink_trays, expected_delink_slots, original_trays):
    expected_slots = expected_delink_slots or []
    submitted_ids = []

    for row in delink_trays or []:
        if isinstance(row, dict):
            raw_tray_id = row.get('tray_id', '')
        else:
            raw_tray_id = _row_get(row, 'tray_id', row)
        tray_id = _tray_id(raw_tray_id)
        if tray_id:
            submitted_ids.append(tray_id)

    if len(submitted_ids) != len(expected_slots):
        raise ValueError('Scan all delink tray slots before submitting.')

    original_rows = _clean_tray_rows(original_trays)
    original_qty_by_id = {row['tray_id']: row['qty'] for row in original_rows}
    seen_trays = set()
    normalized = []

    for index, tray_id in enumerate(submitted_ids):
        if tray_id in seen_trays:
            raise ValueError(f"Duplicate delink tray {tray_id} scanned.")
        if tray_id not in original_qty_by_id:
            raise ValueError(f"Delink tray {tray_id} is not an original tray for this lot.")
        seen_trays.add(tray_id)
        normalized.append({
            'tray_id': tray_id,
            'qty': original_qty_by_id[tray_id],
            'is_delinked': True,
            'slot_no': index + 1,
        })
    return normalized


def normalize_accept_trays(accept_trays, expected_accept_trays, original_trays=None, delink_trays=None):
    rows = _clean_tray_rows(accept_trays)
    expected_rows = _clean_tray_rows(expected_accept_trays)
    expected_qty_by_id = {row['tray_id']: row['qty'] for row in expected_rows}

    if original_trays is not None:
        if len(rows) != len(expected_rows):
            raise ValueError('Scan the accept top tray and all auto-filled accept trays before submitting.')
        if sorted(row['qty'] for row in rows) != sorted(row['qty'] for row in expected_rows):
            raise ValueError('Accept tray quantities do not match backend allocation.')

        original_rows = _clean_tray_rows(original_trays)
        original_qty_by_id = {row['tray_id']: row['qty'] for row in original_rows}
        delink_ids = {
            _tray_id(row.get('tray_id') if isinstance(row, dict) else row)
            for row in (delink_trays or [])
        }

        seen_trays = set()
        for row in rows:
            tray_id = row['tray_id']
            if tray_id in seen_trays:
                raise ValueError(f"Duplicate accept tray {tray_id} scanned.")
            if tray_id in delink_ids:
                raise ValueError(f"Accept tray {tray_id} is already selected as delink tray.")
            if tray_id not in original_qty_by_id:
                raise ValueError(f"Accept tray {tray_id} is not an original tray for this lot.")
            seen_trays.add(tray_id)
        return _mark_top_by_smallest_qty(rows)

    if expected_rows:
        if len(rows) != len(expected_rows):
            raise ValueError('Scan the accept top tray and all auto-filled accept trays before submitting.')
        submitted_ids = {row['tray_id'] for row in rows}
        expected_ids = set(expected_qty_by_id.keys())
        if submitted_ids != expected_ids:
            missing_ids = [tray_id for tray_id in expected_qty_by_id if tray_id not in submitted_ids]
            extra_ids = [row['tray_id'] for row in rows if row['tray_id'] not in expected_ids]
            details = []
            if missing_ids:
                details.append('missing ' + ', '.join(missing_ids))
            if extra_ids:
                details.append('unexpected ' + ', '.join(extra_ids))
            raise ValueError('Accept tray list does not match backend allocation: ' + '; '.join(details))
        for row in rows:
            if row['qty'] != expected_qty_by_id[row['tray_id']]:
                raise ValueError(f"Accept tray {row['tray_id']} qty must be {expected_qty_by_id[row['tray_id']]}")

    seen_trays = set()
    for row in rows:
        if row['tray_id'] in seen_trays:
            raise ValueError(f"Duplicate accept tray {row['tray_id']} scanned.")
        seen_trays.add(row['tray_id'])
    return _mark_top_by_smallest_qty(rows)


def validate_original_tray_coverage(accept_trays, delink_trays, original_trays, reject_trays=None):
    original_ids = {
        row['tray_id']
        for row in _clean_tray_rows(original_trays)
    }
    # A freed original tray reused directly as its own reject container (instead
    # of being delinked separately) also counts as covering that original tray —
    # only reused original IDs count here, not brand-new NB/JB reject trays.
    reused_original_ids = {
        row['tray_id']
        for row in _clean_tray_rows(reject_trays)
        if row['tray_id'] in original_ids
    }
    submitted_ids = {
        row['tray_id']
        for row in _clean_tray_rows(accept_trays)
    } | {
        row['tray_id']
        for row in _clean_tray_rows(delink_trays)
    } | reused_original_ids

    missing_ids = sorted(original_ids - submitted_ids)
    extra_ids = sorted(submitted_ids - original_ids)
    if missing_ids or extra_ids:
        details = []
        if missing_ids:
            details.append('missing ' + ', '.join(missing_ids))
        if extra_ids:
            details.append('unexpected ' + ', '.join(extra_ids))
        raise ValueError('Accept and delink trays must cover the original lot trays: ' + '; '.join(details))


def tray_qty_total(rows):
    return sum(_nq_int(row.get('qty')) for row in rows or [])