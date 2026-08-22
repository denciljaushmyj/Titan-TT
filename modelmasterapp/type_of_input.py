"""Single source of truth for the 'Type of Input' (Fresh / Recovery) display value.

The underlying data lives on ModelMasterCreation.upload_type. All modules that
show a lot/tray/stock row derived (directly or via TotalStockModel.batch_id)
from a ModelMasterCreation batch should use these helpers instead of
re-deriving the Fresh/Recovery label inline.
"""

from modelmasterapp.models import TotalStockModel


def label_for_upload_type(upload_type):
    """Map the stored upload_type value to its display label."""
    return 'Recovery' if upload_type == 'recovery' else 'Fresh'


def get_type_of_input_for_batch(batch):
    """batch: a ModelMasterCreation instance (or None)."""
    if not batch:
        return 'Fresh'
    return label_for_upload_type(getattr(batch, 'upload_type', None))


def get_type_of_input_map(lot_ids):
    """Bulk-resolve Type of Input for rows keyed by lot_id (TotalStockModel.lot_id).

    Returns {lot_id: 'Fresh' | 'Recovery'}. Missing lot_ids are simply absent
    from the map; callers should default to 'Fresh' on lookup miss.
    """
    lot_ids = [lot_id for lot_id in (lot_ids or []) if lot_id]
    if not lot_ids:
        return {}
    rows = (
        TotalStockModel.objects
        .filter(lot_id__in=lot_ids)
        .values('lot_id', 'batch_id__upload_type')
    )
    return {
        row['lot_id']: label_for_upload_type(row['batch_id__upload_type'])
        for row in rows
    }
