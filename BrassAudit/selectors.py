"""
Brass Audit selectors.

Read-only queryset builders for the Brass Audit module.
"""

from django.db.models import Exists, F, OuterRef, Q

from modelmasterapp.models import TotalStockModel

from .models import Brass_Audit_Draft_Store, Brass_Audit_Rejection_ReasonStore


def get_picktable_base_queryset():
    """
    Return the same base queryset used by the Brass Audit pick table.

    Global scan must use this selector so tray scans resolve only to lots that
    are actually active and visible in Brass Audit.
    """
    has_draft_subquery = Exists(
        Brass_Audit_Draft_Store.objects.filter(lot_id=OuterRef('lot_id'))
    )
    draft_type_subquery = Brass_Audit_Draft_Store.objects.filter(
        lot_id=OuterRef('lot_id')
    ).values('draft_type')[:1]
    brass_rejection_qty_subquery = Brass_Audit_Rejection_ReasonStore.objects.filter(
        lot_id=OuterRef('lot_id')
    ).values('total_rejection_quantity')[:1]

    return TotalStockModel.objects.select_related(
        'batch_id',
        'batch_id__model_stock_no',
        'batch_id__version',
        'batch_id__location',
    ).filter(
        batch_id__total_batch_quantity__gt=0
    ).annotate(
        wiping_required=F('batch_id__model_stock_no__wiping_required'),
        has_draft=has_draft_subquery,
        draft_type=draft_type_subquery,
        brass_rejection_total_qty=brass_rejection_qty_subquery,
    ).filter(
        Q(brass_qc_accptance=True, brass_audit_accptance__isnull=True) |
        Q(brass_qc_accptance=True, brass_audit_accptance=False) |
        Q(brass_qc_few_cases_accptance=True, brass_onhold_picking=False) |
        Q(brass_audit_few_cases_accptance=True, brass_audit_onhold_picking=True)
    ).exclude(
        brass_audit_rejection=True
    ).exclude(
        Q(brass_audit_few_cases_accptance=True, brass_audit_onhold_picking=False)
    ).exclude(
        next_process_module='Split Completed'
    ).exclude(
        remove_lot=True
    )