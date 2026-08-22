"""
Brass QC Lot Service — lot ID generation and child lot creation.

Handles:
- generate_lot_id()              → new lot ID in enterprise LID format
- create_partial_accept_child()  → accept child lot for PARTIAL split
- create_partial_reject_child()  → reject child lot for PARTIAL split

Rule: Only lot creation/mutation writes here. No HTTP layer.
"""

import uuid
import logging
import time
from datetime import datetime

from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lot ID generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_lot_id(submission_type=""):
    """
    Generate unique lot ID in enterprise LID format.

    Format: LID + YYYYMMDDHHMMSS + NNNNNN (microseconds, zero-padded) + XXXX (random hex)
    Example: LID202604232030570000015a3c

    DB-safe: retries up to 20 times with exponential backoff and random suffix.
    Uses UUID-based random component to guarantee uniqueness even during rapid
    concurrent calls within same microsecond (e.g., PARTIAL generating 2 lot IDs).
    """
    from modelmasterapp.models import TotalStockModel

    for attempt in range(20):
        now = datetime.now()
        # Get random 4-char hex suffix to guarantee uniqueness
        random_suffix = uuid.uuid4().hex[:4]
        lot_id = f"LID{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}{random_suffix}"
        
        if not TotalStockModel.objects.filter(lot_id=lot_id).exists():
            logger.debug(f"[generate_lot_id] Generated: {lot_id} (attempt {attempt + 1})")
            return lot_id
        
        # Exponential backoff: 1ms, 2ms, 4ms, etc.
        time.sleep(0.001 * (2 ** min(attempt, 3)))

    # Final fallback — should almost never reach here
    logger.error(f"[generate_lot_id] Failed to generate unique lot_id after 20 attempts, using UUID")
    random_suffix = uuid.uuid4().hex[:8]
    now = datetime.now()
    return f"LID{now.strftime('%Y%m%d%H%M%S')}{random_suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Partial split — child lot creation
# ─────────────────────────────────────────────────────────────────────────────

def create_partial_accept_child(
    stock,
    t_accept_lot_id,
    accepted_qty,
    accepted_trays,
    submission,
    user,
):
    """
    Creates the accepted child lot for a PARTIAL Brass QC submission.

    Writes:
      - TotalStockModel (child_accept)
      - BrassAuditTrayId (one per accepted tray)
      - BrassTrayId (one per accepted tray)
      - Brass_Qc_Accepted_TrayID_Store (upsert per tray)
      - Brass_Qc_Accepted_TrayScan
      - BrassQC_PartialAcceptLot
    
    Idempotent: If child lot already exists (e.g., from retry), returns existing record.
    """
    from modelmasterapp.models import TotalStockModel
    from BrassAudit.models import BrassAuditTrayId
    from django.db import IntegrityError
    from ..models import (
        BrassTrayId,
        Brass_Qc_Accepted_TrayID_Store,
        Brass_Qc_Accepted_TrayScan,
        BrassQC_PartialAcceptLot,
    )

    # Check if child already exists (e.g., from previous failed attempt)
    existing = TotalStockModel.objects.filter(lot_id=t_accept_lot_id).first()
    if existing:
        logger.warning(
            f"[lot_service] Accept child already exists: lot={t_accept_lot_id}, "
            f"returning existing record (idempotent)"
        )
        return existing

    try:
        child_accept = TotalStockModel.objects.create(
            lot_id=t_accept_lot_id,
            batch_id=stock.batch_id,
            model_stock_no=stock.model_stock_no,
            version=stock.version,
            polish_finish=stock.polish_finish,
            plating_color=stock.plating_color,
            total_stock=accepted_qty,
            total_IP_accpeted_quantity=accepted_qty,
            brass_physical_qty=accepted_qty,
            accepted_Ip_stock=True,
            brass_qc_accepted_qty_verified=True,
            last_process_module="Brass QC",
            next_process_module="Brass Audit",
            current_stage="Brass QC",
            last_process_date_time=timezone.now(),
            bq_last_process_date_time=timezone.now(),
            brass_qc_accepted_qty=accepted_qty,
            brass_qc_accptance=True,
        )
    except IntegrityError as e:
        logger.error(f"[lot_service] IntegrityError creating accept child: {e}")
        # Fallback: fetch existing if race condition occurred
        child_accept = TotalStockModel.objects.get(lot_id=t_accept_lot_id)
        logger.warning(f"[lot_service] Fallback: using existing child lot {t_accept_lot_id}")
        return child_accept

    for tray in accepted_trays:
        BrassAuditTrayId.objects.create(
            lot_id=t_accept_lot_id,
            tray_id=tray['tray_id'],
            tray_quantity=tray['qty'],
            batch_id=stock.batch_id,
            top_tray=tray.get('is_top', False),
        )
        BrassTrayId.objects.create(
            lot_id=t_accept_lot_id,
            tray_id=tray['tray_id'],
            tray_quantity=tray['qty'],
            batch_id=stock.batch_id,
            top_tray=tray.get('is_top', False),
        )
        Brass_Qc_Accepted_TrayID_Store.objects.update_or_create(
            tray_id=tray['tray_id'],
            defaults={
                'lot_id': t_accept_lot_id,
                'tray_qty': tray['qty'],
                'user': user,
                'is_save': True,
                'is_draft': False,
            },
        )

    Brass_Qc_Accepted_TrayScan.objects.create(
        lot_id=t_accept_lot_id,
        accepted_tray_quantity=str(accepted_qty),
        user=user,
    )

    BrassQC_PartialAcceptLot.objects.create(
        new_lot_id=t_accept_lot_id,
        parent_lot_id=submission.lot_id,
        parent_batch_id=stock.batch_id.batch_id if stock.batch_id else '',
        parent_submission=submission,
        accepted_qty=accepted_qty,
        accept_trays_count=len(accepted_trays),
        trays_snapshot=accepted_trays,
        created_by=user,
    )

    logger.info(
        f"[lot_service] Accept child created: lot={t_accept_lot_id}, "
        f"qty={accepted_qty}, trays={len(accepted_trays)}"
    )
    return child_accept


def create_partial_reject_child(
    stock,
    t_reject_lot_id,
    rejected_qty,
    rejected_trays,
    submission,
    rejection_reasons,
    remarks,
    user,
):
    """
    Creates the rejected child lot for a PARTIAL Brass QC submission.

    Writes:
      - TotalStockModel (child_reject)
      - IQFTrayId (one per rejected tray)
      - BrassTrayId (one per rejected tray)
      - Brass_QC_Rejection_ReasonStore
      - BrassQC_PartialRejectLot
    
    Idempotent: If child lot already exists (e.g., from retry), returns existing record.
    """
    from modelmasterapp.models import TotalStockModel
    from IQF.models import IQFTrayId
    from django.db import IntegrityError
    from ..models import (
        BrassTrayId,
        Brass_QC_Rejection_ReasonStore,
        Brass_QC_Rejection_Table,
        BrassQC_PartialRejectLot,
    )

    # Check if child already exists (e.g., from previous failed attempt)
    existing = TotalStockModel.objects.filter(lot_id=t_reject_lot_id).first()
    if existing:
        logger.warning(
            f"[lot_service] Reject child already exists: lot={t_reject_lot_id}, "
            f"returning existing record (idempotent)"
        )
        return existing

    try:
        child_reject = TotalStockModel.objects.create(
            lot_id=t_reject_lot_id,
            batch_id=stock.batch_id,
            model_stock_no=stock.model_stock_no,
            version=stock.version,
            polish_finish=stock.polish_finish,
            plating_color=stock.plating_color,
            total_stock=rejected_qty,
            total_IP_accpeted_quantity=rejected_qty,
            brass_physical_qty=rejected_qty,
            accepted_Ip_stock=True,
            brass_qc_accepted_qty_verified=True,
            last_process_module="Brass QC",
            next_process_module="IQF",
            current_stage="Brass QC",
            last_process_date_time=timezone.now(),
            bq_last_process_date_time=timezone.now(),
            brass_qc_after_rejection_qty=rejected_qty,
            brass_qc_rejection=True,
            send_brass_audit_to_iqf=True,
        )
    except IntegrityError as e:
        logger.error(f"[lot_service] IntegrityError creating reject child: {e}")
        # Fallback: fetch existing if race condition occurred
        child_reject = TotalStockModel.objects.get(lot_id=t_reject_lot_id)
        logger.warning(f"[lot_service] Fallback: using existing child lot {t_reject_lot_id}")
        return child_reject

    for tray in rejected_trays:
        IQFTrayId.objects.create(
            lot_id=t_reject_lot_id,
            tray_id=tray['tray_id'],
            tray_quantity=tray['qty'],
            batch_id=stock.batch_id,
            IP_tray_verified=True,
            top_tray=tray.get('is_top', False),
        )
        BrassTrayId.objects.create(
            lot_id=t_reject_lot_id,
            tray_id=tray['tray_id'],
            tray_quantity=tray['qty'],
            batch_id=stock.batch_id,
            top_tray=tray.get('is_top', False),
        )

    Brass_QC_Rejection_ReasonStore.objects.create(
        lot_id=t_reject_lot_id,
        user=user,
        total_rejection_quantity=rejected_qty,
        batch_rejection=False,
    )

    # Build rejection reasons dict for snapshot
    reasons_dict = {}
    for r in (rejection_reasons or []):
        rid = r.get("reason_id") or r.get("id", "")
        try:
            reason_obj = Brass_QC_Rejection_Table.objects.get(id=rid)
            reasons_dict[reason_obj.rejection_reason_id or str(rid)] = {
                "reason": reason_obj.rejection_reason,
                "qty": int(r.get("qty", 0)),
            }
        except Brass_QC_Rejection_Table.DoesNotExist:
            pass

    BrassQC_PartialRejectLot.objects.create(
        new_lot_id=t_reject_lot_id,
        parent_lot_id=submission.lot_id,
        parent_batch_id=stock.batch_id.batch_id if stock.batch_id else '',
        parent_submission=submission,
        rejected_qty=rejected_qty,
        reject_trays_count=len(rejected_trays),
        rejection_reasons=reasons_dict,
        trays_snapshot=rejected_trays,
        remarks=remarks or None,
        created_by=user,
    )

    logger.info(
        f"[lot_service] Reject child created: lot={t_reject_lot_id}, "
        f"qty={rejected_qty}, trays={len(rejected_trays)}"
    )
    return child_reject


def create_full_reject_child(
    stock,
    t_lot_id,
    rejected_qty,
    rejected_trays,
    submission,
    rejection_reasons,
    remarks,
    user,
):
    """
    Creates the rejected child lot for a FULL_REJECT Brass QC submission.

    Mirrors create_partial_reject_child but for FULL_REJECT (the entire
    parent lot is rejected and forwarded to IQF as a NEW transition lot).

    Writes:
      - TotalStockModel  (new child stock under t_lot_id, routed to IQF)
      - IQFTrayId        (one per rejected tray under t_lot_id)
      - BrassTrayId      (one per rejected tray under t_lot_id)
      - Brass_QC_Rejection_ReasonStore (rejection ledger under t_lot_id)
      - BrassQC_PartialRejectLot       (snapshot record under t_lot_id)

    The original parent stock is closed by the caller via
    get_stock_flag_updates(FULL_REJECT) which sets
    is_split=True, remove_lot=True so the parent does NOT appear in IQF.
    
    Idempotent: If child lot already exists (e.g., from retry), returns existing record.
    """
    from modelmasterapp.models import TotalStockModel
    from IQF.models import IQFTrayId
    from django.db import IntegrityError
    from ..models import (
        BrassTrayId,
        Brass_QC_Rejection_ReasonStore,
        Brass_QC_Rejection_Table,
        BrassQC_PartialRejectLot,
    )

    # Check if child already exists (e.g., from previous failed attempt)
    existing = TotalStockModel.objects.filter(lot_id=t_lot_id).first()
    if existing:
        logger.warning(
            f"[lot_service] Full reject child already exists: lot={t_lot_id}, "
            f"returning existing record (idempotent)"
        )
        return existing

    try:
        child_reject = TotalStockModel.objects.create(
            lot_id=t_lot_id,
            batch_id=stock.batch_id,
            model_stock_no=stock.model_stock_no,
            version=stock.version,
            polish_finish=stock.polish_finish,
            plating_color=stock.plating_color,
            total_stock=rejected_qty,
            total_IP_accpeted_quantity=rejected_qty,
            brass_physical_qty=rejected_qty,
            accepted_Ip_stock=True,
            brass_qc_accepted_qty_verified=True,
            last_process_module="Brass QC",
            next_process_module="IQF",
            current_stage="Brass QC",
            last_process_date_time=timezone.now(),
            bq_last_process_date_time=timezone.now(),
            brass_qc_after_rejection_qty=rejected_qty,
            # ✅ CRITICAL: Do NOT set brass_qc_rejection=True on the transition lot.
            # That flag causes this lot to appear in the Brass QC Completed table
            # (duplicate row). The transition lot belongs to IQF only.
            # send_brass_audit_to_iqf=True is sufficient for IQF pick table visibility.
            # The PARENT lot (closed with is_split+remove_lot) correctly carries
            # brass_qc_rejection=True for the Brass QC Completed view.
            brass_qc_rejection=False,
            send_brass_audit_to_iqf=True,
        )
    except IntegrityError as e:
        logger.error(f"[lot_service] IntegrityError creating full reject child: {e}")
        # Fallback: fetch existing if race condition occurred
        child_reject = TotalStockModel.objects.get(lot_id=t_lot_id)
        logger.warning(f"[lot_service] Fallback: using existing child lot {t_lot_id}")
        return child_reject

    for tray in rejected_trays:
        IQFTrayId.objects.update_or_create(
            lot_id=t_lot_id,
            tray_id=tray['tray_id'],
            defaults={
                'tray_quantity': tray['qty'],
                'batch_id': stock.batch_id,
                'IP_tray_verified': True,
                'top_tray': tray.get('is_top', False),
                'rejected_tray': False,
                'delink_tray': False,
            },
        )
        BrassTrayId.objects.update_or_create(
            lot_id=t_lot_id,
            tray_id=tray['tray_id'],
            defaults={
                'tray_quantity': tray['qty'],
                'batch_id': stock.batch_id,
                'top_tray': tray.get('is_top', False),
                'rejected_tray': False,
                'delink_tray': False,
            },
        )

    Brass_QC_Rejection_ReasonStore.objects.create(
        lot_id=t_lot_id,
        user=user,
        total_rejection_quantity=rejected_qty,
        batch_rejection=True,
    )

    # Build rejection reasons snapshot (handle both reason_id lookup and FULL fallback)
    reasons_dict = {}
    for r in (rejection_reasons or []):
        rid = r.get("reason_id") or r.get("id")
        if rid:
            try:
                reason_obj = Brass_QC_Rejection_Table.objects.get(id=rid)
                reasons_dict[reason_obj.rejection_reason_id or str(rid)] = {
                    "reason": reason_obj.rejection_reason,
                    "qty": int(r.get("qty", 0)),
                }
                continue
            except Brass_QC_Rejection_Table.DoesNotExist:
                pass
        reasons_dict[str(rid or "FULL")] = {
            "reason": r.get("reason", "FULL LOT REJECTED"),
            "qty": int(r.get("qty", 0)),
        }

    BrassQC_PartialRejectLot.objects.create(
        new_lot_id=t_lot_id,
        parent_lot_id=submission.lot_id,
        parent_batch_id=stock.batch_id.batch_id if stock.batch_id else '',
        parent_submission=submission,
        rejected_qty=rejected_qty,
        reject_trays_count=len(rejected_trays),
        rejection_reasons=reasons_dict,
        trays_snapshot=rejected_trays,
        remarks=remarks or None,
        created_by=user,
    )

    logger.info(
        f"[lot_service] FULL_REJECT child created: lot={t_lot_id}, "
        f"parent={submission.lot_id}, qty={rejected_qty}, trays={len(rejected_trays)}"
    )
    return child_reject
