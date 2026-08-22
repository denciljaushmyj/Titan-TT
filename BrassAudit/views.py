from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer
from django.shortcuts import render
from django.db.models import OuterRef, Subquery, Exists, F, Sum, Count
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.templatetags.static import static
import math
from modelmasterapp.models import *
from DayPlanning.models import *
from InputScreening.models import *
from .models import *
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import traceback
from rest_framework import status
from django.http import JsonResponse
import json
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.http import require_GET
from math import ceil
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from IQF.models import *
from Brass_QC.models import *
from django.utils import timezone
from datetime import timedelta
import datetime
import pytz
import logging
from django.db import transaction
from .selectors import get_picktable_base_queryset
from watchcase_tracker.perf_logger import time_stage
from modelmasterapp.type_of_input import get_type_of_input_for_batch

logger = logging.getLogger(__name__)


def _get_sorted_model_images(model_master):
    """Return model images with front-view priority when helper is available.

    The production server may not contain ``modelmasterapp.image_utils``.
    In that case, use the existing ManyToMany ordering instead of crashing the
    entire Brass Audit page.
    """
    if not model_master:
        return []

    model_images = model_master.images.all()

    try:
        from modelmasterapp.image_utils import sort_images_front_first
    except ImportError:
        logger.warning(
            "modelmasterapp.image_utils is unavailable; using default model image order"
        )
        return model_images

    try:
        return sort_images_front_first(model_images)
    except Exception:
        logger.exception(
            "Unable to sort model images; using default model image order"
        )
        return model_images


# ═══════════════════════════════════════════════════════════════
# Brass Audit Pick Table View
# ═══════════════════════════════════════════════════════════════
@method_decorator(login_required, name='dispatch')
class BrassAuditPickTableView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'BrassAudit/BrassAudit_PickTable.html'

    def get(self, request):
        user = request.user
        is_admin = user.groups.filter(name='Admin').exists() if user.is_authenticated else False

        sort = request.GET.get('sort')
        order = request.GET.get('order', 'asc')

        sort_field_mapping = {
            'serial_number': 'lot_id',
            'brass_audit_last_process_date_time': 'brass_audit_last_process_date_time',
            'plating_stk_no': 'batch_id__plating_stk_no',
            'polishing_stk_no': 'batch_id__polishing_stk_no',
            'plating_color': 'batch_id__plating_color',
            'category': 'batch_id__category',
            'polish_finish': 'batch_id__polish_finish',
            'tray_capacity': 'batch_id__tray_capacity',
            'vendor_location': 'batch_id__vendor_internal',
            'no_of_trays': 'batch_id__tray_capacity',
            'lot_qty': 'brass_qc_accepted_qty',
            'brass_audit_physical_qty': 'brass_audit_physical_qty',
            'brass_audit_accepted_qty': 'brass_audit_accepted_qty',
            'reject_qty': 'brass_rejection_total_qty',
        }

        brass_rejection_reasons = Brass_Audit_Rejection_Table.objects.all()

        queryset = get_picktable_base_queryset()

        if sort and sort in sort_field_mapping:
            field = sort_field_mapping[sort]
            if order == 'desc':
                field = '-' + field
            queryset = queryset.order_by(field)
        else:
            queryset = queryset.order_by('-bq_last_process_date_time', '-lot_id')

        page_number = request.GET.get('page', 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)

        master_data = []
        for stock_obj in page_obj.object_list:
            batch = stock_obj.batch_id
            brass_qc_accepted_qty = stock_obj.brass_qc_accepted_qty or 0

            data = {
                'batch_id': batch.batch_id,
                'lot_id': stock_obj.lot_id,
                'date_time': batch.date_time,
                'model_stock_no__model_no': batch.model_stock_no.model_no,
                'plating_color': batch.plating_color,
                'polish_finish': batch.polish_finish,
                'version__version_name': batch.version.version_name if batch.version else '',
                'vendor_internal': batch.vendor_internal,
                'location__location_name': batch.location.location_name if batch.location else '',
                'tray_type': batch.tray_type,
                'tray_capacity': batch.tray_capacity,
                'wiping_required': stock_obj.wiping_required,
                'brass_onhold_picking': stock_obj.brass_onhold_picking,
                'stock_lot_id': stock_obj.lot_id,
                'brass_audit_accepted_qty': stock_obj.brass_audit_accepted_qty,
                'brass_audit_accepted_qty_verified': stock_obj.brass_audit_accepted_qty_verified,
                'brass_qc_accepted_qty': stock_obj.brass_qc_accepted_qty,
                'brass_audit_missing_qty': stock_obj.brass_audit_missing_qty,
                'brass_audit_physical_qty': stock_obj.brass_audit_physical_qty,
                'brass_audit_physical_qty_edited': stock_obj.brass_audit_physical_qty_edited,
                'accepted_Ip_stock': stock_obj.accepted_Ip_stock,
                'rejected_ip_stock': stock_obj.rejected_ip_stock,
                'few_cases_accepted_Ip_stock': stock_obj.few_cases_accepted_Ip_stock,
                'accepted_tray_scan_status': stock_obj.accepted_tray_scan_status,
                'BA_pick_remarks': stock_obj.BA_pick_remarks,
                'Bq_pick_remarks': stock_obj.Bq_pick_remarks,
                'brass_qc_accptance': stock_obj.brass_qc_accptance,
                'brass_accepted_tray_scan_status': stock_obj.brass_accepted_tray_scan_status,
                'brass_audit_accptance': getattr(stock_obj, 'brass_audit_accptance', False),
                'brass_audit_rejection': stock_obj.brass_audit_rejection,
                'brass_qc_few_cases_accptance': stock_obj.brass_qc_few_cases_accptance,
                'brass_audit_few_cases_accptance': stock_obj.brass_audit_few_cases_accptance,
                'brass_audit_onhold_picking': stock_obj.brass_audit_onhold_picking,
                'brass_audit_draft': stock_obj.brass_audit_draft,
                'iqf_acceptance': stock_obj.iqf_acceptance,
                'send_brass_qc': stock_obj.send_brass_qc,
                'send_brass_audit_to_qc': stock_obj.send_brass_audit_to_qc,
                'bq_last_process_date_time': stock_obj.bq_last_process_date_time,
                'brass_audit_last_process_date_time': stock_obj.brass_audit_last_process_date_time,
                'iqf_last_process_date_time': stock_obj.iqf_last_process_date_time,
                'iqf_accepted_qty': stock_obj.iqf_accepted_qty,
                'brass_audit_hold_lot': stock_obj.brass_audit_hold_lot,
                'brass_audit_holding_reason': stock_obj.brass_audit_holding_reason,
                'brass_audit_release_lot': stock_obj.brass_audit_release_lot,
                'brass_audit_release_reason': stock_obj.brass_audit_release_reason,
                'brass_audit_hold_by': getattr(getattr(stock_obj, 'brass_audit_hold_by', None), 'username', ''),
                'brass_audit_hold_at': timezone.localtime(getattr(stock_obj, 'brass_audit_hold_at')).strftime("%d-%b-%Y %I:%M %p") if getattr(stock_obj, 'brass_audit_hold_at', None) else '',
                'brass_audit_release_by': getattr(getattr(stock_obj, 'brass_audit_release_by', None), 'username', ''),
                'brass_audit_release_at': timezone.localtime(getattr(stock_obj, 'brass_audit_release_at')).strftime("%d-%b-%Y %I:%M %p") if getattr(stock_obj, 'brass_audit_release_at', None) else '',
                'has_draft': stock_obj.has_draft,
                'draft_type': stock_obj.draft_type,
                'brass_rejection_total_qty': stock_obj.brass_rejection_total_qty,
                'plating_stk_no': batch.plating_stk_no,
                'polishing_stk_no': batch.polishing_stk_no,
                'category': batch.category,
                'last_process_module': stock_obj.last_process_module,
                'type_of_input': get_type_of_input_for_batch(batch),
            }

            # AQL Sampling Plan
            aql_plan = AQLSamplingPlan.objects.filter(
                lot_qty_from__lte=brass_qc_accepted_qty,
                lot_qty_to__gte=brass_qc_accepted_qty
            ).first()
            data['aql_limit'] = float(aql_plan.aql_limit) if aql_plan else None
            data['sample_qty'] = aql_plan.sample_qty if aql_plan else None

            master_data.append(data)

        for data in master_data:
            brass_qc_accepted_qty = data.get('brass_qc_accepted_qty', 0)
            tray_capacity = data.get('tray_capacity', 0)
            data['vendor_location'] = f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"
            lot_id = data.get('stock_lot_id')

            # LOT-INDEPENDENT tray resolution: only current lot's BrassAuditTrayId
            audit_trays = BrassAuditTrayId.objects.filter(
                lot_id=lot_id, delink_tray=False, rejected_tray=False
            )
            if audit_trays.exists():
                ba_lot_qty = audit_trays.aggregate(total=Sum('tray_quantity'))['total'] or 0
                ba_no_of_trays = audit_trays.count()
                data['display_accepted_qty'] = ba_lot_qty
                data['no_of_trays'] = ba_no_of_trays
            else:
                # Fallback: use brass_qc_accepted_qty (what QC sent)
                if brass_qc_accepted_qty > 0:
                    data['display_accepted_qty'] = brass_qc_accepted_qty
                elif data.get('brass_audit_accepted_qty', 0) > 0:
                    data['display_accepted_qty'] = data['brass_audit_accepted_qty']
                elif data.get('iqf_accepted_qty', 0) > 0:
                    data['display_accepted_qty'] = data['iqf_accepted_qty']
                else:
                    data['display_accepted_qty'] = 0

                display_qty = data.get('display_accepted_qty', 0)
                if tray_capacity > 0 and display_qty > 0:
                    data['no_of_trays'] = math.ceil(display_qty / tray_capacity)
                else:
                    data['no_of_trays'] = 0

            brass_audit_physical_qty = data.get('brass_audit_physical_qty') or 0
            brass_rejection_total_qty = data.get('brass_rejection_total_qty') or 0
            is_delink_only = (brass_audit_physical_qty > 0 and
                              brass_rejection_total_qty >= brass_audit_physical_qty and
                              data.get('brass_audit_onhold_picking', False))
            data['is_delink_only'] = is_delink_only

            # Model images
            batch_obj = ModelMasterCreation.objects.filter(batch_id=data['batch_id']).first()
            images = []
            if batch_obj:
                model_master = batch_obj.model_stock_no
                for img in _get_sorted_model_images(model_master):
                    if img.master_image:
                        images.append(img.master_image.url)
            if not images:
                images = [static('assets/images/imagePlaceholder.jpg')]
            data['model_images'] = images

            data['available_qty'] = data.get('brass_audit_accepted_qty') if data.get('brass_audit_accepted_qty') and data.get('brass_audit_accepted_qty') > 0 else (data.get('brass_audit_physical_qty') if data.get('brass_audit_physical_qty') and data.get('brass_audit_physical_qty') > 0 else data.get('brass_qc_accepted_qty', 0))

            # ✅ Fallback: Display most recent available date/time for "Last Date and Time" column
            # Priority: brass_audit_last_process_date_time → bq_last_process_date_time → iqf_last_process_date_time
            display_last_datetime = (
                data.get('brass_audit_last_process_date_time') or
                data.get('bq_last_process_date_time') or
                data.get('iqf_last_process_date_time')
            )
            data['display_last_process_date_time'] = display_last_datetime

            # Backend-computed flags
            data['can_delete'] = (
                not data.get('brass_audit_accptance') and
                not data.get('brass_audit_rejection') and
                not data.get('brass_accepted_tray_scan_status') and
                not data.get('brass_audit_few_cases_accptance') and
                data.get('brass_audit_accepted_qty_verified', False)
            )

            # Circle status
            if data.get('brass_audit_onhold_picking') or data.get('brass_audit_draft'):
                data['qc_circle'] = 'HALF'
            elif data.get('brass_audit_rejection') or data.get('brass_audit_accptance') or data.get('brass_audit_few_cases_accptance'):
                data['qc_circle'] = 'GREEN'
            else:
                data['qc_circle'] = 'GRAY'

            # Action state
            if data.get('brass_audit_onhold_picking') and data.get('is_delink_only'):
                data['action_state'] = 'ONHOLD_DELINK'
            elif data.get('brass_audit_onhold_picking') and not data.get('is_delink_only'):
                data['action_state'] = 'ONHOLD_TOPTRAY'
            elif data.get('brass_audit_rejection') or data.get('brass_audit_few_cases_accptance'):
                data['action_state'] = 'REJECTED'
            else:
                data['action_state'] = 'DEFAULT'

            # Lot status pill
            if data.get('brass_audit_onhold_picking') or data.get('brass_audit_draft'):
                data['lot_status'] = 'Draft'
            elif data.get('brass_audit_hold_lot'):
                data['lot_status'] = 'On Hold'
            elif data.get('brass_audit_rejection') or data.get('brass_audit_few_cases_accptance') or data.get('brass_audit_accptance'):
                data['lot_status'] = 'Yet to Release'
            elif data.get('brass_audit_accepted_qty_verified'):
                data['lot_status'] = 'Yet to Release'
            else:
                data['lot_status'] = 'Yet to Start'

            # Fallbacks
            if not data.get('brass_audit_physical_qty'):
                data['brass_audit_physical_qty'] = data.get('brass_physical_qty', 0)
            if not data.get('brass_audit_missing_qty'):
                data['brass_audit_missing_qty'] = data.get('brass_missing_qty', 0)

        # Remove duplicate lot rows (keep first occurrence) — preserves existing master_data order
        seen = set()
        unique_master = []
        for d in master_data:
            lid = d.get('stock_lot_id') or d.get('lot_id')
            if lid not in seen:
                seen.add(lid)
                unique_master.append(d)
        master_data = unique_master

        # Debug: log what records remain after dedupe
        try:
            print(f"[BrassAuditPickTable] Total master_data records after dedupe: {len(master_data)}")
            print("[BrassAuditPickTable] Processed lot_ids:", [d.get('stock_lot_id') or d.get('lot_id') for d in master_data])
        except Exception:
            pass

        context = {
            
            'master_data': master_data,
            'page_obj': page_obj,
            'paginator': paginator,
            'user': user,
            'is_admin': is_admin,
            'brass_rejection_reasons': brass_rejection_reasons,
            'pick_table_count': len(master_data),
        }
        return Response(context, template_name=self.template_name)
        # Deduplicate rows by lot id (keep first occurrence)



# ═══════════════════════════════════════════════════════════════
# Stage display helper — Brass Audit Completed table
# ═══════════════════════════════════════════════════════════════
_VALID_STAGE_NAMES = {
    'Input Screening', 'IQF', 'Brass QC', 'Brass Audit',
    'Jig Loading', 'Jig Unloading', 'Nickel Inspection',
    'Spider Spindle', 'Day Planning', 'Inprocess Inspection',
    'Nickel Audit',
}

def _compute_brass_audit_display_stage(stock_obj):
    """
    Computes the Current Stage pill value for the Brass Audit Completed table.

    Rule: only advance the display to the next stage once the lot has actually
    been worked on there (draft saved or submitted).  While the lot is just
    sitting in the next stage's pick table it still shows 'Brass Audit'.

    Supports FULL_ACCEPT (own lot → Jig Loading),
              FULL_REJECT (own lot → Brass QC),
              PARTIAL     (child accept lot → Jig Loading,
                           parent row stays in Completed table).
    """
    # Resolved next module: follow child accept lot for PARTIAL, own for the rest
    _npm = stock_obj.child_accept_stage or stock_obj.next_process_module
    _fallback = stock_obj.last_process_module or 'Brass Audit'

    if not _npm or _npm not in _VALID_STAGE_NAMES:
        return _fallback

    if _npm == 'Jig Loading':
        # Has Jig Loading actually been started?
        # Own-lot flags cover FULL_ACCEPT; child_jig_active covers PARTIAL child.
        _own_jig = bool(stock_obj.jig_draft or stock_obj.Jig_Load_completed)
        _child_jig = bool(getattr(stock_obj, 'child_jig_active', False))
        if not (_own_jig or _child_jig):
            return _fallback

    elif _npm == 'Brass QC':
        # FULL_REJECT: lot sent back to Brass QC — has it been touched?
        _bq_active = bool(
            stock_obj.brass_draft or
            stock_obj.brass_qc_accptance or
            stock_obj.brass_qc_rejection or
            stock_obj.brass_qc_few_cases_accptance
        )
        if not _bq_active:
            return _fallback

    # Any other valid module (Jig Unloading, Nickel Inspection, …):
    # The lot has clearly progressed past Jig Loading → show as-is.
    return _npm


# ═══════════════════════════════════════════════════════════════
# Brass Audit Completed Table View
# ═══════════════════════════════════════════════════════════════
@method_decorator(login_required, name='dispatch')
class BrassAuditCompletedView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'BrassAudit/BrassAudit_Completed.html'

    def get(self, request):
        user = request.user

        sort = request.GET.get('sort')
        order = request.GET.get('order', 'asc')

        sort_field_mapping = {
            'serial_number': 'lot_id',
            'date_time': 'brass_audit_last_process_date_time',
            'plating_stk_no': 'batch_id__plating_stk_no',
            'polishing_stk_no': 'batch_id__polishing_stk_no',
            'plating_color': 'batch_id__plating_color',
            'category': 'batch_id__category',
            'polish_finish': 'batch_id__polish_finish',
            'tray_capacity': 'batch_id__tray_capacity',
            'vendor_location': 'batch_id__vendor_internal',
            'no_of_trays': 'batch_id__no_of_trays',
            'accepted_qty': 'brass_audit_accepted_qty',
            'rejected_qty': 'brass_audit_rejection_qty',
            'process_status': 'last_process_module',
            'lot_status': 'last_process_module',
            'current_stage': 'next_process_module',
            'remarks': 'BA_pick_remarks',
        }

        # Timing labels below are logged automatically by RequestPerf whenever
        # this request ends up slow (see watchcase_tracker/perf_logger.py) -
        # they pinpoint which block inside this view is the actual 8s cost.
        with time_stage(request, 'BAC_DATE_SETUP'):
            tz = pytz.timezone("Asia/Kolkata")
            now_local = timezone.now().astimezone(tz)
            today = now_local.date()
            yesterday = today - timedelta(days=1)

            from_date_str = request.GET.get('from_date')
            to_date_str = request.GET.get('to_date')

            if from_date_str and to_date_str:
                try:
                    from_date = datetime.datetime.strptime(from_date_str, '%Y-%m-%d').date()
                    to_date = datetime.datetime.strptime(to_date_str, '%Y-%m-%d').date()
                except ValueError:
                    from_date = yesterday
                    to_date = today
            else:
                from_date = yesterday
                to_date = today

            from_datetime = timezone.make_aware(datetime.datetime.combine(from_date, datetime.datetime.min.time()))
            to_datetime = timezone.make_aware(datetime.datetime.combine(to_date, datetime.datetime.max.time()))

        with time_stage(request, 'BAC_QUERYSET_BUILD'):
            brass_audit_rejection_qty_subquery = Brass_Audit_Rejection_ReasonStore.objects.filter(
                lot_id=OuterRef('lot_id')
            ).values('total_rejection_quantity')[:1]

            # Subquery: live next_process_module of the accepted child lot (PARTIAL splits)
            # For FULL_ACCEPT/FULL_REJECT: brass_audit_transition_accept_lot_id is NULL → returns None → falls back to own next_process_module
            # Prefer the child's current_stage SSOT (kept live by every downstream module)
            # so a child that progressed past Jig Loading (e.g. Nickel Wiping) is reflected
            # here, not just its routing hint (next_process_module).
            child_accept_stage_subquery = TotalStockModel.objects.filter(
                lot_id=OuterRef('brass_audit_transition_accept_lot_id')
            ).annotate(
                _live_stage=Coalesce('current_stage', 'next_process_module', 'last_process_module')
            ).values('_live_stage')[:1]

            # Subquery: has the child accept lot (PARTIAL) actually been worked on in Jig Loading?
            # Combined with own-lot check covers FULL_ACCEPT case too.
            child_jig_active_subquery = Exists(
                TotalStockModel.objects.filter(
                    lot_id=OuterRef('brass_audit_transition_accept_lot_id')
                ).filter(Q(jig_draft=True) | Q(Jig_Load_completed=True))
            )

            # ✅ FIX: Only show lots with actual Brass_Audit_Submission records
            # Prevents unprocessed lots (just moved through stages) from appearing in Completed table
            has_valid_submission = Exists(
                Brass_Audit_Submission.objects.filter(
                    lot_id=OuterRef('lot_id'),
                    is_completed=True
                )
            )

            queryset = TotalStockModel.objects.select_related(
                'batch_id',
                'batch_id__model_stock_no',
                'batch_id__version',
                'batch_id__location'
            ).filter(
                batch_id__total_batch_quantity__gt=0,
                brass_audit_last_process_date_time__range=(from_datetime, to_datetime)
            ).annotate(
                brass_audit_rejection_qty=brass_audit_rejection_qty_subquery,
                child_accept_stage=child_accept_stage_subquery,
                child_jig_active=child_jig_active_subquery,
            ).filter(
                Q(brass_audit_accptance=True) |
                Q(brass_audit_rejection=True) |
                Q(brass_audit_few_cases_accptance=True, brass_audit_onhold_picking=False)
            ).filter(
                has_valid_submission
            )

        with time_stage(request, 'BAC_EXCLUDE_IDS'):
            # BUG2 FIX: Exclude child lots from partial splits — only parent summary row.
            # ✅ FIX (Issue 2): Re-entry lots (child lots that later submitted their own BA
            # FULL_ACCEPT or FULL_REJECT) MUST NOT be excluded even if they appear in
            # _child_accept_ids/_child_reject_ids from an earlier BA PARTIAL cycle.
            _child_accept_ids = set(
                Brass_Audit_Submission.objects.filter(
                    submission_type='PARTIAL', is_completed=True,
                    transition_accept_lot_id__isnull=False
                ).values_list('transition_accept_lot_id', flat=True)
            )
            _child_reject_ids = set(
                Brass_Audit_Submission.objects.filter(
                    submission_type='PARTIAL', is_completed=True,
                    transition_reject_lot_id__isnull=False
                ).values_list('transition_reject_lot_id', flat=True)
            )
            # Lots that submitted their own BA result (FULL_ACCEPT / FULL_REJECT) are re-entry
            # lots — they must appear in BA CT regardless of being a historical child.
            _reentry_ids = set(
                Brass_Audit_Submission.objects.filter(
                    submission_type__in=['FULL_ACCEPT', 'FULL_REJECT'],
                    is_completed=True,
                ).values_list('lot_id', flat=True)
            )
            _exclude_accept = _child_accept_ids - _reentry_ids
            _exclude_reject = _child_reject_ids - _reentry_ids
            queryset = queryset.exclude(
                Q(lot_id__in=_exclude_accept) | Q(lot_id__in=_exclude_reject)
            )

        with time_stage(request, 'BAC_SORT_PAGINATE'):
            if sort and sort in sort_field_mapping:
                field = sort_field_mapping[sort]
                if order == 'desc':
                    field = '-' + field
                queryset = queryset.order_by(field)
            else:
                queryset = queryset.order_by('-brass_audit_last_process_date_time', '-lot_id')

            page_number = request.GET.get('page', 1)
            paginator = Paginator(queryset, 10)
            page_obj = paginator.get_page(page_number)

        with time_stage(request, 'BAC_ROW_BUILD'):
            master_data = []
            for stock_obj in page_obj.object_list:
                batch = stock_obj.batch_id

                # A completed Brass Audit row is released only after the
                # destination module has actually started work.  Merely routing
                # it to Jig Loading (or back to Brass QC) remains Yet to Release.
                # A PARTIAL split freezes the parent row's own current_stage at the
                # moment of split; the real progress lives on the accepted child lot
                # (own lot_id, keeps advancing through Jig Loading/Nickel Wiping/etc).
                # Compare both and show whichever is further along so the parent row
                # never displays a stale stage once its child has moved on.
                from modelmasterapp.stage_service import most_advanced_stage
                current_stage_display = most_advanced_stage(
                    stock_obj.current_stage or _compute_brass_audit_display_stage(stock_obj),
                    getattr(stock_obj, 'child_accept_stage', None),
                )
                if getattr(stock_obj, 'brass_audit_hold_lot', False):
                    lot_status = 'On Hold'
                elif stock_obj.next_process_module == 'Split Completed':
                    lot_status = 'Split Completed'
                elif current_stage_display != 'Brass Audit':
                    lot_status = 'Released'
                else:
                    lot_status = 'Yet to Release'

                data = {
                    'batch_id': batch.batch_id,
                    'lot_id': stock_obj.lot_id,
                    'date_time': batch.date_time,
                    'model_stock_no__model_no': batch.model_stock_no.model_no if batch.model_stock_no else '',
                    'plating_color': batch.plating_color,
                    'polish_finish': batch.polish_finish,
                    'version__version_name': batch.version.version_name if batch.version else '',
                    'vendor_internal': batch.vendor_internal,
                    'location__location_name': batch.location.location_name if batch.location else '',
                    'tray_type': batch.tray_type,
                    'tray_capacity': batch.tray_capacity,
                    'stock_lot_id': stock_obj.lot_id,
                    'last_process_module': stock_obj.last_process_module,
                    # Use current_stage when set (new data); fall back to dynamic computation
                    # for legacy lots that pre-date the current_stage field.
                    'next_process_module': current_stage_display,
                    'lot_status': lot_status,
                    'brass_audit_accepted_qty_verified': stock_obj.brass_audit_accepted_qty_verified,
                    'brass_audit_accepted_qty': stock_obj.brass_audit_accepted_qty,
                    'brass_audit_rejection_qty': stock_obj.brass_audit_rejection_qty,
                    'brass_audit_missing_qty': stock_obj.brass_audit_missing_qty,
                    'brass_audit_physical_qty': stock_obj.brass_audit_physical_qty,
                    'brass_qc_accepted_qty': stock_obj.brass_qc_accepted_qty,
                    'accepted_Ip_stock': stock_obj.accepted_Ip_stock,
                    'rejected_ip_stock': stock_obj.rejected_ip_stock,
                    'few_cases_accepted_Ip_stock': stock_obj.few_cases_accepted_Ip_stock,
                    'accepted_tray_scan_status': stock_obj.accepted_tray_scan_status,
                    'BA_pick_remarks': stock_obj.BA_pick_remarks,
                    'BA_pick_remarks_has_text': bool((stock_obj.BA_pick_remarks or '').strip()),
                    'brass_audit_accptance': stock_obj.brass_audit_accptance,
                    'brass_accepted_tray_scan_status': stock_obj.brass_accepted_tray_scan_status,
                    'brass_audit_rejection': stock_obj.brass_audit_rejection,
                    'brass_audit_few_cases_accptance': stock_obj.brass_audit_few_cases_accptance,
                    'brass_audit_onhold_picking': stock_obj.brass_audit_onhold_picking,
                    'brass_qc_accepted_qty': stock_obj.brass_qc_accepted_qty,
                    'brass_audit_last_process_date_time': stock_obj.brass_audit_last_process_date_time,
                    'plating_stk_no': batch.plating_stk_no,
                    'polishing_stk_no': batch.polishing_stk_no,
                    'category': batch.category,
                    'no_of_trays': 0,
                    'type_of_input': get_type_of_input_for_batch(batch),
                }
                master_data.append(data)

        with time_stage(request, 'BAC_ROW_ENRICH'):
            for data in master_data:
                brass_qc_accepted_qty = data.get('brass_qc_accepted_qty', 0)
                tray_capacity = data.get('tray_capacity', 0)
                data['vendor_location'] = f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"
                lot_id = data.get('stock_lot_id')

                # ✅ FIX ERR 2 & ERR 5: Fetch lot qty and quantities dynamically from submission data
                submission = Brass_Audit_Submission.objects.filter(lot_id=lot_id, is_completed=True).order_by('-created_at').first()
                if submission:
                    data['display_lot_qty'] = submission.total_lot_qty
                    data['display_accepted_qty'] = submission.accepted_qty
                    data['display_rejected_qty'] = submission.rejected_qty
                    data['submission_type'] = submission.submission_type
                    logger.info(f"[BrassAuditCompleted] Lot {lot_id}: Fetched from submission - lot_qty={submission.total_lot_qty}, accept={submission.accepted_qty}, reject={submission.rejected_qty}")
                else:
                    # ✅ ENHANCED FALLBACK: Multi-tier fallback for lot qty
                    # Priority: brass_qc_accepted_qty → brass_audit_physical_qty → brass_audit_accepted_qty → total_stock
                    fallback_lot_qty = 0
                    fallback_source = "none"

                    if brass_qc_accepted_qty and brass_qc_accepted_qty > 0:
                        fallback_lot_qty = brass_qc_accepted_qty
                        fallback_source = "brass_qc_accepted_qty"
                    elif stock_obj.brass_audit_physical_qty and stock_obj.brass_audit_physical_qty > 0:
                        fallback_lot_qty = stock_obj.brass_audit_physical_qty
                        fallback_source = "brass_audit_physical_qty"
                    elif stock_obj.brass_audit_accepted_qty and stock_obj.brass_audit_accepted_qty > 0:
                        fallback_lot_qty = stock_obj.brass_audit_accepted_qty
                        fallback_source = "brass_audit_accepted_qty"
                    elif stock_obj.total_stock and stock_obj.total_stock > 0:
                        fallback_lot_qty = stock_obj.total_stock
                        fallback_source = "total_stock"

                    data['display_lot_qty'] = fallback_lot_qty
                    data['display_accepted_qty'] = data.get('brass_audit_accepted_qty', 0)
                    data['display_rejected_qty'] = data.get('brass_audit_rejection_qty', 0)
                    data['submission_type'] = ''

                    if fallback_lot_qty > 0:
                        logger.info(f"[BrassAuditCompleted] Lot {lot_id}: No submission found, using fallback source '{fallback_source}' with qty={fallback_lot_qty}")
                    else:
                        logger.warning(f"[BrassAuditCompleted] Lot {lot_id}: No submission found and all fallback sources are 0 or null")

                display_qty = data.get('display_lot_qty', 0)
                if tray_capacity > 0 and display_qty > 0:
                    data['no_of_trays'] = math.ceil(display_qty / tray_capacity)
                else:
                    data['no_of_trays'] = 0

                batch_obj = ModelMasterCreation.objects.filter(batch_id=data['batch_id']).first()
                images = []
                if batch_obj and batch_obj.model_stock_no:
                    for img in _get_sorted_model_images(batch_obj.model_stock_no):
                        if img.master_image:
                            images.append(img.master_image.url)
                if not images:
                    images = [static('assets/images/imagePlaceholder.jpg')]
                data['model_images'] = images

                if data.get('brass_audit_physical_qty') and data.get('brass_audit_physical_qty') > 0:
                    data['available_qty'] = data['brass_audit_physical_qty']
                else:
                    data['available_qty'] = data.get('display_lot_qty', 0)

                data['lot_remarks'] = ''

        with time_stage(request, 'BAC_CONTEXT_BUILD'):
            context = {
                'master_data': master_data,
                'page_obj': page_obj,
                'paginator': paginator,
                'user': user,
                'from_date': from_date.strftime('%Y-%m-%d'),
                'to_date': to_date.strftime('%Y-%m-%d'),
                'date_filter_applied': bool(from_date_str and to_date_str),
            }
        return Response(context, template_name=self.template_name)


# ═══════════════════════════════════════════════════════════════
# Brass Audit Reject Table View
# ═══════════════════════════════════════════════════════════════
@method_decorator(login_required, name='dispatch')
class BrassAuditRejectTableView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'BrassAudit/BrassAudit_RejectTable.html'

    def get(self, request):
        user = request.user

        tz = pytz.timezone("Asia/Kolkata")
        now_local = timezone.now().astimezone(tz)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')

        if from_date_str and to_date_str:
            try:
                from_date = datetime.datetime.strptime(from_date_str, '%Y-%m-%d').date()
                to_date = datetime.datetime.strptime(to_date_str, '%Y-%m-%d').date()
            except ValueError:
                from_date = yesterday
                to_date = today
        else:
            from_date = yesterday
            to_date = today

        from_datetime = timezone.make_aware(datetime.datetime.combine(from_date, datetime.datetime.min.time()))
        to_datetime = timezone.make_aware(datetime.datetime.combine(to_date, datetime.datetime.max.time()))

        brass_audit_rejection_qty_sub = Brass_Audit_Rejection_ReasonStore.objects.filter(
            lot_id=OuterRef('lot_id')
        ).values('total_rejection_quantity')[:1]

        queryset = TotalStockModel.objects.select_related(
            'batch_id',
            'batch_id__model_stock_no',
            'batch_id__version',
            'batch_id__location'
        ).filter(
            batch_id__total_batch_quantity__gt=0,
            brass_audit_last_process_date_time__range=(from_datetime, to_datetime)
        ).filter(
            # ✅ FIX ERR 2: Include both FULL_REJECT and PARTIAL_REJECT
            Q(brass_audit_rejection=True) | Q(brass_audit_few_cases_accptance=True)
        ).annotate(
            brass_audit_rejection_qty=brass_audit_rejection_qty_sub,
        )

        # BUG4 FIX: Exclude child lots — only parent summary row in reject table
        _child_accept_ids = Brass_Audit_Submission.objects.filter(
            submission_type='PARTIAL', is_completed=True,
            transition_accept_lot_id__isnull=False
        ).values_list('transition_accept_lot_id', flat=True)
        _child_reject_ids = Brass_Audit_Submission.objects.filter(
            submission_type='PARTIAL', is_completed=True,
            transition_reject_lot_id__isnull=False
        ).values_list('transition_reject_lot_id', flat=True)
        queryset = queryset.exclude(
            Q(lot_id__in=_child_accept_ids) | Q(lot_id__in=_child_reject_ids)
        )

        queryset = queryset.order_by('-brass_audit_last_process_date_time', '-lot_id')

        page_number = request.GET.get('page', 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)

        master_data = []
        for stock_obj in page_obj.object_list:
            batch = stock_obj.batch_id
            data = {
                'batch_id': batch.batch_id,
                'lot_id': stock_obj.lot_id,
                'stock_lot_id': stock_obj.lot_id,
                'date_time': batch.date_time,
                'model_stock_no__model_no': batch.model_stock_no.model_no if batch.model_stock_no else '',
                'plating_color': batch.plating_color,
                'polish_finish': batch.polish_finish,
                'version__version_name': batch.version.version_name if batch.version else '',
                'vendor_internal': batch.vendor_internal,
                'location__location_name': batch.location.location_name if batch.location else '',
                'tray_type': batch.tray_type,
                'tray_capacity': batch.tray_capacity,
                'plating_stk_no': batch.plating_stk_no,
                'polishing_stk_no': batch.polishing_stk_no,
                'category': batch.category,
                'type_of_input': get_type_of_input_for_batch(batch),
                'brass_audit_last_process_date_time': stock_obj.brass_audit_last_process_date_time,
                'brass_audit_physical_qty': stock_obj.brass_audit_physical_qty,
                'brass_qc_accepted_qty': stock_obj.brass_qc_accepted_qty,
                'brass_audit_rejection_qty': getattr(stock_obj, 'brass_audit_rejection_qty', None) or 0,
                'brass_audit_accepted_qty': stock_obj.brass_audit_accepted_qty,
                'brass_audit_few_cases_accptance': stock_obj.brass_audit_few_cases_accptance,
                'brass_audit_accptance': stock_obj.brass_audit_accptance,
                'last_process_module': stock_obj.last_process_module,
                'next_process_module': stock_obj.next_process_module,
                'BA_pick_remarks': stock_obj.BA_pick_remarks,
            }
            data['vendor_location'] = f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"

            batch_obj = ModelMasterCreation.objects.filter(batch_id=data['batch_id']).first()
            images = []
            if batch_obj and batch_obj.model_stock_no:
                for img in _get_sorted_model_images(batch_obj.model_stock_no):
                    if img.master_image:
                        images.append(img.master_image.url)
            if not images:
                images = [static('assets/images/imagePlaceholder.jpg')]
            data['model_images'] = images

            # ✅ FIX ERR 3: Fetch remarks dynamically from multiple sources
            lot_id = data.get('stock_lot_id')
            
            # Fetch submission data for exact quantities and remarks
            submission = Brass_Audit_Submission.objects.filter(lot_id=lot_id, is_completed=True).order_by('-created_at').first()
            if submission:
                data['display_reject_qty'] = submission.rejected_qty
                # ✅ Try to get remarks from submission snapshot_data first
                remarks_from_submission = ''
                if submission.snapshot_data and submission.snapshot_data.get('remarks'):
                    remarks_from_submission = submission.snapshot_data.get('remarks', '').strip()
                logger.info(f"[BrassAuditReject] Lot {lot_id}: Fetched reject qty={submission.rejected_qty}, remarks_from_submission={remarks_from_submission}")
            else:
                data['display_reject_qty'] = data.get('brass_audit_rejection_qty', 0)
                remarks_from_submission = ''
                logger.warning(f"[BrassAuditReject] Lot {lot_id}: No submission found")
            
            # Fetch rejection reasons and remarks
            reason_store = Brass_Audit_Rejection_ReasonStore.objects.filter(lot_id=lot_id).order_by('-id').first()
            if reason_store:
                reasons = reason_store.rejection_reason.all()
                reason_letters = []
                for r in reasons:
                    if r.rejection_reason:
                        reason_letters.append(r.rejection_reason[0].upper())
                data['rejection_reason_letters'] = reason_letters
                data['batch_rejection'] = reason_store.batch_rejection
                # ✅ Use reason store remarks if submission remarks is empty
                data['lot_rejected_comment'] = reason_store.lot_rejected_comment or remarks_from_submission or ''
            else:
                data['rejection_reason_letters'] = []
                data['batch_rejection'] = False
                # ✅ Use submission remarks as fallback
                data['lot_rejected_comment'] = remarks_from_submission or ''
            
            # Calculate no of trays based on reject qty
            reject_qty = data.get('display_reject_qty', 0)
            tray_capacity = data.get('tray_capacity', 0)
            if tray_capacity > 0 and reject_qty > 0:
                data['no_of_trays'] = math.ceil(reject_qty / tray_capacity)
            else:
                data['no_of_trays'] = 0

            master_data.append(data)

        context = {
            'master_data': master_data,
            'page_obj': page_obj,
            'paginator': paginator,
            'user': user,
            'from_date': from_date.strftime('%Y-%m-%d'),
            'to_date': to_date.strftime('%Y-%m-%d'),
        }
        return Response(context, template_name=self.template_name)


# ═══════════════════════════════════════════════════════════════
# Shared Tray Resolver — LOT-INDEPENDENT
# ═══════════════════════════════════════════════════════════════
def _resolve_lot_trays_audit(lot_id):
    """
    Shared tray resolver for Brass Audit — single source of truth.
    Returns (tray_data_list, source_name, total_qty).
    STRICTLY uses current lot data only — no cross-stage history.

    Priority order:
      1. BrassAuditTrayId       — Brass Audit's own table (highest priority)
      2. Brass_QC_Submission    — BQC accept snapshot (canonical for IS→BQC→BA flow)
      3. IS_PartialAcceptLot    — IS partial accept snapshot (correct post-IS qty)
      4. BrassTrayId            — Brass QC tray table (rejected trays excluded)
      5. IPTrayId               — Input Screening tray table (rejected trays excluded)
      6. TrayId                 — Global tray table (rejected/delinked excluded)
      7. AcceptedStore          — Last-resort fallback
      8. IQFTrayId              — IQF-returned lots
    """
    from Brass_QC.models import Brass_QC_Submission
    from InputScreening.models import IS_PartialAcceptLot, IPTrayId

    tray_data = []
    source = "BrassAuditTrayId"

    # Step 1: BrassAuditTrayId (Brass Audit's own table)
    trays = BrassAuditTrayId.objects.filter(lot_id=lot_id).order_by('-top_tray', 'id')
    if trays.exists():
        tray_data = [
            {"tray_id": t.tray_id, "qty": t.tray_quantity or 0,
             "is_rejected": t.rejected_tray, "is_top": t.top_tray, "is_delinked": t.delink_tray}
            for t in trays
        ]

    # Step 2: Brass_QC_Submission accept snapshot
    # This is the canonical source for IS→BQC→BA flow — contains exactly what BQC accepted
    # with correct post-IS-rejection quantities (no original TrayId pollution).
    if not tray_data:
        source = "BQCSubmission"
        bqc_sub = Brass_QC_Submission.objects.filter(
            lot_id=lot_id,
            submission_type__in=['FULL_ACCEPT', 'PARTIAL']
        ).order_by('-id').first()
        if bqc_sub:
            if bqc_sub.submission_type == 'FULL_ACCEPT' and bqc_sub.full_accept_data:
                trays_raw = bqc_sub.full_accept_data.get('trays', [])
            elif bqc_sub.submission_type == 'PARTIAL' and bqc_sub.partial_accept_data:
                trays_raw = bqc_sub.partial_accept_data.get('trays', [])
            else:
                trays_raw = []
            if trays_raw:
                tray_data = [
                    {
                        "tray_id": t["tray_id"],
                        "qty": int(t.get("qty", 0) or 0),
                        "is_rejected": False,
                        "is_top": bool(t.get("is_top", False)),
                        "is_delinked": False,
                    }
                    for t in trays_raw
                    if t.get("tray_id")
                ]

    # Step 3: IS_PartialAcceptLot snapshot (correct post-IS-rejection qty)
    if not tray_data:
        source = "IS_PartialAcceptLot"
        is_pa = IS_PartialAcceptLot.objects.filter(new_lot_id=lot_id).first()
        if is_pa and is_pa.trays_snapshot:
            tray_data = [
                {
                    "tray_id": t.get("tray_id"),
                    "qty": int(t.get("qty", 0) or 0),
                    "is_rejected": False,
                    "is_top": bool(t.get("top_tray", False)),
                    "is_delinked": False,
                }
                for t in (is_pa.trays_snapshot or [])
                if t.get("tray_id") and int(t.get("qty", 0) or 0) > 0
            ]

    # Step 4: BrassTrayId (Brass QC tray table) — exclude rejected and delinked
    if not tray_data:
        source = "BrassTrayId"
        brass_trays = BrassTrayId.objects.filter(
            lot_id=lot_id, delink_tray=False, rejected_tray=False
        ).order_by('-top_tray', 'id')
        if brass_trays.exists():
            tray_data = [
                {"tray_id": t.tray_id, "qty": t.tray_quantity or 0,
                 "is_rejected": False,
                 "is_top": bool(t.top_tray),
                 "is_delinked": False}
                for t in brass_trays
            ]

    # Step 5: IPTrayId (Input Screening tray table) — exclude rejected and delinked
    if not tray_data:
        source = "IPTrayId"
        ip_trays = IPTrayId.objects.filter(
            lot_id=lot_id, tray_quantity__gt=0,
            rejected_tray=False, delink_tray=False
        ).order_by('-top_tray', 'id')
        if ip_trays.exists():
            tray_data = [
                {"tray_id": t.tray_id, "qty": t.tray_quantity or 0,
                 "is_rejected": False,
                 "is_top": bool(t.top_tray),
                 "is_delinked": False}
                for t in ip_trays
            ]

    # Step 6: Fallback to TrayId (global table) — exclude rejected and delinked
    if not tray_data:
        source = "TrayId"
        trays = TrayId.objects.filter(
            lot_id=lot_id, tray_quantity__gt=0,
            rejected_tray=False, delink_tray=False
        ).order_by('-top_tray', 'id')
        tray_data = [
            {"tray_id": t.tray_id, "qty": t.tray_quantity or 0,
             "is_rejected": False,
             "is_top": t.top_tray,
             "is_delinked": False}
            for t in trays
        ]

    # Step 7: Final fallback to Accepted Store
    if not tray_data:
        source = "AcceptedStore"
        accepted = Brass_Audit_Accepted_TrayID_Store.objects.filter(lot_id=lot_id)
        tray_data = [
            {"tray_id": t.tray_id, "qty": t.tray_qty or 0,
             "is_rejected": False, "is_top": False, "is_delinked": False}
            for t in accepted
        ]

    # Step 8: IQFTrayId fallback — for IQF-accepted child lots that have no BrassAuditTrayId
    if not tray_data:
        source = "IQFTrayId"
        iqf_trays = IQFTrayId.objects.filter(lot_id=lot_id, delink_tray=False).order_by('-top_tray', 'id')
        tray_data = [
            {
                "tray_id": t.tray_id,
                "qty": int(t.remaining_qty or 0) if (t.remaining_qty or 0) > 0 else int(t.tray_quantity or 0),
                "is_rejected": bool(t.rejected_tray),
                "is_top": bool(t.top_tray),
                "is_delinked": False,
            }
            for t in iqf_trays
        ]

    total_qty = sum(t['qty'] for t in tray_data)

    # Compute status for each tray (backend-driven)
    for t in tray_data:
        if t.get('is_delinked'):
            t['status'] = 'DELINK'
        elif t.get('is_rejected') and t.get('is_top'):
            t['status'] = 'REJECT_TOP'
        elif t.get('is_rejected'):
            t['status'] = 'REJECT'
        elif t.get('is_top'):
            t['status'] = 'ACCEPT_TOP'
        else:
            t['status'] = 'ACCEPT'

    return tray_data, source, total_qty


# ═══════════════════════════════════════════════════════════════
# Lot Qty - Verification Toggle
# ═══════════════════════════════════════════════════════════════
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brass_audit_toggle_verified(request):
    lot_id = request.data.get('lot_id')
    verified = request.data.get('verified', False)

    if not lot_id:
        return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)

    ts = TotalStockModel.objects.filter(lot_id=lot_id).first()
    if not ts:
        return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

    ts.brass_audit_accepted_qty_verified = bool(verified)
    update_fields = ['brass_audit_accepted_qty_verified']

    if bool(verified) and ts.last_process_module != 'Brass Audit':
        ts.last_process_module = 'Brass Audit'
        ts.current_stage = 'Brass Audit'
        update_fields.append('last_process_module')
        update_fields.append('current_stage')

    ts.save(update_fields=update_fields)

    # ── Bin icon activation rule (mirrors pick-table can_delete) ──
    can_delete = (
        not ts.brass_audit_accptance and
        not ts.brass_audit_rejection and
        not ts.brass_accepted_tray_scan_status and
        not ts.brass_audit_few_cases_accptance and
        ts.brass_audit_accepted_qty_verified
    )

    return JsonResponse({
        "success": True,
        "lot_id": lot_id,
        "brass_audit_accepted_qty_verified": ts.brass_audit_accepted_qty_verified,
        "last_process_module": ts.last_process_module,
        "can_delete": can_delete,
    })


# ═══════════════════════════════════════════════════════════════
# Hard Delete: Bin icon action (admin-gated, can_delete-gated)
# ═══════════════════════════════════════════════════════════════
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brass_audit_delete_batch(request):
    """
    Permanently deletes a lot's TotalStockModel row (and its tray
    assignments) from the Brass Audit pick table.

    Only allowed when:
      - the requesting user is in the Admin group, AND
      - the lot satisfies the same can_delete rule shown on the pick table
        (not accepted / not rejected / not tray-scanned / qty verified)
    Both checks are enforced here — the frontend Bin icon is a display
    affordance only, never the source of truth.
    """
    is_admin = request.user.groups.filter(name='Admin').exists()
    if not is_admin:
        return JsonResponse({"success": False, "error": "Admin access required."}, status=403)

    lot_id = (request.data.get('stock_lot_id') or request.data.get('lot_id') or '').strip()
    if not lot_id:
        return JsonResponse({"success": False, "error": "stock_lot_id is required"}, status=400)

    ts = TotalStockModel.objects.filter(lot_id=lot_id).first()
    if not ts:
        return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

    can_delete = (
        not ts.brass_audit_accptance and
        not ts.brass_audit_rejection and
        not ts.brass_accepted_tray_scan_status and
        not ts.brass_audit_few_cases_accptance and
        ts.brass_audit_accepted_qty_verified
    )
    if not can_delete:
        return JsonResponse({"success": False, "error": "This lot can no longer be deleted."}, status=409)

    with transaction.atomic():
        BrassAuditTrayId.objects.filter(lot_id=lot_id).delete()
        ts.delete()  # cascades related rows via TotalStockModel.delete() override

    logger.info("Brass Audit Delete Batch: lot_id=%s deleted by user=%s", lot_id, request.user)
    return JsonResponse({"success": True, "message": "Lot deleted successfully.", "lot_id": lot_id})


# ═══════════════════════════════════════════════════════════════
# Hold / Unhold Toggle with Remark
# ═══════════════════════════════════════════════════════════════
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brass_audit_hold_unhold(request):
    lot_id = request.data.get('lot_id')
    action = request.data.get('action')
    remark = request.data.get('remark', '').strip()

    if not lot_id:
        return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
    if action not in ('hold', 'unhold'):
        return JsonResponse({"success": False, "error": "action must be 'hold' or 'unhold'"}, status=400)
    if not remark:
        return JsonResponse({"success": False, "error": "Remark is required"}, status=400)
    if len(remark) > 50:
        return JsonResponse({"success": False, "error": "Remark must be 50 characters or less"}, status=400)

    ts = TotalStockModel.objects.filter(lot_id=lot_id).first()
    if not ts:
        return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

    now = timezone.now()
    if action == 'hold':
        ts.brass_audit_hold_lot = True
        ts.brass_audit_holding_reason = remark
        if hasattr(ts, 'brass_audit_hold_by'):
            ts.brass_audit_hold_by = request.user
        if hasattr(ts, 'brass_audit_hold_at'):
            ts.brass_audit_hold_at = now
        ts.brass_audit_release_lot = False
        ts.brass_audit_release_reason = ''
    else:
        ts.brass_audit_hold_lot = False
        ts.brass_audit_release_reason = remark
        if hasattr(ts, 'brass_audit_release_by'):
            ts.brass_audit_release_by = request.user
        if hasattr(ts, 'brass_audit_release_at'):
            ts.brass_audit_release_at = now
        ts.brass_audit_release_lot = True

    update_fields = [
        'brass_audit_hold_lot',
        'brass_audit_holding_reason',
        'brass_audit_release_lot',
        'brass_audit_release_reason',
    ]
    if hasattr(ts, 'brass_audit_hold_by'):
        update_fields.append('brass_audit_hold_by')
    if hasattr(ts, 'brass_audit_hold_at'):
        update_fields.append('brass_audit_hold_at')
    if hasattr(ts, 'brass_audit_release_by'):
        update_fields.append('brass_audit_release_by')
    if hasattr(ts, 'brass_audit_release_at'):
        update_fields.append('brass_audit_release_at')
    ts.save(update_fields=update_fields)

    logger.info(f"[BrassAudit] Hold/Unhold: lot_id={lot_id}, action={action}, remark={remark}, user={request.user}")

    return JsonResponse({
        "success": True,
        "lot_id": lot_id,
        "action": action,
        "holding_reason": ts.brass_audit_holding_reason or '',
        "release_reason": ts.brass_audit_release_reason or '',
        "hold_lot": ts.brass_audit_hold_lot,
        "release_lot": ts.brass_audit_release_lot,
        "hold_by": getattr(getattr(ts, 'brass_audit_hold_by', None), 'username', ''),
        "hold_at": timezone.localtime(getattr(ts, 'brass_audit_hold_at')).strftime("%d-%b-%Y %I:%M %p") if getattr(ts, 'brass_audit_hold_at', None) else '',
        "release_by": getattr(getattr(ts, 'brass_audit_release_by', None), 'username', ''),
        "release_at": timezone.localtime(getattr(ts, 'brass_audit_release_at')).strftime("%d-%b-%Y %I:%M %p") if getattr(ts, 'brass_audit_release_at', None) else '',
        "message": f"Lot {'held' if action == 'hold' else 'released'} successfully.",
    })


# ═══════════════════════════════════════════════════════════════
# Rejection Reasons - Dynamic Fetch
# ═══════════════════════════════════════════════════════════════
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_audit_rejection_reasons(request):
    reasons = Brass_Audit_Rejection_Table.objects.all().order_by('rejection_reason_id')
    data = [
        {"id": r.id, "reason_id": r.rejection_reason_id, "reason": r.rejection_reason}
        for r in reasons
    ]
    return JsonResponse({"success": True, "reasons": data})


# ═══════════════════════════════════════════════════════════════
# Tray Reuse Logic
# ═══════════════════════════════════════════════════════════════
def compute_reuse_trays(trays, reject_qty):
    trays_sorted = sorted(trays, key=lambda x: (not x.get('is_top', False), x.get('tray_id', '')))
    reuse_trays = []
    updated_trays = []
    remaining_reject = reject_qty

    for tray in trays_sorted:
        tray_qty = tray["qty"]
        if remaining_reject <= 0:
            updated_trays.append({**tray, "remaining_qty": tray_qty})
            continue
        if remaining_reject >= tray_qty:
            remaining_reject -= tray_qty
            updated_trays.append({**tray, "used_qty": tray_qty, "remaining_qty": 0, "status": "REJECT_FULL"})
            reuse_trays.append(tray["tray_id"])
        else:
            updated_trays.append({**tray, "used_qty": remaining_reject, "remaining_qty": tray_qty - remaining_reject, "status": "REJECT_PARTIAL"})
            remaining_reject = 0

    return {"reuse_trays": reuse_trays, "updated_trays": updated_trays}


# ═══════════════════════════════════════════════════════════════
# Brass Audit Unified API Endpoint
# ═══════════════════════════════════════════════════════════════
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brass_audit_action(request):
    """
    UNIFIED Brass Audit API — single entry point for all actions.
    Actions: GET_TRAYS, GET_SUBMISSION_TRAYS, ALLOCATE, VALIDATE_TRAY,
             GET_REASONS, SAVE_DRAFT, GET_DRAFT, FULL_ACCEPT, FULL_REJECT,
             PARTIAL, PROCESS, SAVE_REMARK
    """
    action = request.data.get('action', '').strip()

    if action == 'GET_TRAYS':
        lot_id = request.data.get('lot_id')
        if not lot_id:
            return JsonResponse({"error": "lot_id is required"}, status=400)
        try:
            stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
        except TotalStockModel.DoesNotExist:
            return JsonResponse({"error": "Lot not found"}, status=404)

        # LOT-INDEPENDENT: only resolve current lot's tray data
        tray_data, source, total_qty = _resolve_lot_trays_audit(lot_id)

        tray_capacity = 0
        if stock.batch_id:
            tray_capacity = stock.batch_id.tray_capacity or 0

        logger.info(f"[AUDIT:GET_TRAYS] lot_id={lot_id}, source={source}, trays={len(tray_data)}, total_qty={total_qty}")
        return JsonResponse({
            "lot_id": lot_id,
            "batch_id": stock.batch_id.batch_id if stock.batch_id else "",
            "total_qty": total_qty,
            "tray_capacity": tray_capacity,
            "source": source,
            "trays": tray_data,
        })

    elif action == 'GET_SUBMISSION_TRAYS':
        lot_id = request.data.get('lot_id')
        if not lot_id:
            return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
        submission = Brass_Audit_Submission.objects.filter(lot_id=lot_id, is_completed=True).order_by('-created_at').first()
        if not submission:
            return JsonResponse({"success": True, "lot_id": lot_id, "trays": [],
                                 "accepted_qty": 0, "rejected_qty": 0, "total_lot_qty": 0, "submission_type": ""})

        trays = []
        accept_data = submission.full_accept_data or submission.partial_accept_data or {}
        reject_data = submission.full_reject_data or submission.partial_reject_data or {}

        accept_qty_map = {}
        accept_top_map = {}
        for t in (accept_data.get('trays') or []):
            tid = t.get("tray_id", "")
            if tid:
                accept_qty_map[tid] = int(t.get("qty") or 0)
                accept_top_map[tid] = bool(t.get("is_top", False))

        reject_qty_map = {}
        for t in (reject_data.get('trays') or []):
            tid = t.get("tray_id", "")
            if tid:
                reject_qty_map[tid] = int(t.get("qty") or 0)

        original_qty_map = {}
        for bt in BrassAuditTrayId.objects.filter(lot_id=lot_id):
            if bt.tray_id:
                original_qty_map[bt.tray_id] = int(bt.tray_quantity or 0)
        if not original_qty_map:
            for ti in TrayId.objects.filter(lot_id=lot_id, tray_quantity__gt=0):
                original_qty_map[ti.tray_id] = int(ti.tray_quantity or 0)

        delink_trays = []
        for orig_tid, orig_qty in original_qty_map.items():
            if orig_qty <= 0:
                continue
            used = accept_qty_map.get(orig_tid, 0) + reject_qty_map.get(orig_tid, 0)
            residual = orig_qty - used
            if residual > 0:
                delink_trays.append({
                    "tray_id": orig_tid, "tray_quantity": residual,
                    "rejected_tray": False, "delink_tray": True,
                    "top_tray": False, "is_top_tray": False,
                })

        for tid, qty in accept_qty_map.items():
            trays.append({
                "tray_id": tid, "tray_quantity": qty,
                "rejected_tray": False, "delink_tray": False,
                "top_tray": accept_top_map.get(tid, False),
                "is_top_tray": accept_top_map.get(tid, False),
            })
        for tid, qty in reject_qty_map.items():
            trays.append({
                "tray_id": tid, "tray_quantity": qty,
                "rejected_tray": True, "delink_tray": False,
                "top_tray": False, "is_top_tray": False,
            })
        trays.extend(delink_trays)

        return JsonResponse({
            "success": True, "lot_id": lot_id,
            "submission_type": submission.submission_type,
            "accepted_qty": submission.accepted_qty,
            "rejected_qty": submission.rejected_qty,
            "total_lot_qty": submission.total_lot_qty,
            "trays": trays,
        })

    elif action == 'ALLOCATE':
        lot_id = request.data.get('lot_id')
        rejected_qty = int(request.data.get('rejected_qty', 0))
        if not lot_id:
            return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
        try:
            stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
        except TotalStockModel.DoesNotExist:
            return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

        tray_data, source, total_qty = _resolve_lot_trays_audit(lot_id)
        active_trays = [t for t in tray_data if not t.get('is_delinked')]
        tray_capacity = stock.batch_id.tray_capacity or 0 if stock.batch_id else 0

        if rejected_qty < 0 or rejected_qty > total_qty:
            return JsonResponse({"success": False, "error": "Invalid rejected_qty"}, status=400)
        accepted_qty = total_qty - rejected_qty

        def compute_slots(qty, capacity):
            if qty <= 0 or capacity <= 0:
                return []
            full_trays = qty // capacity
            remainder = qty % capacity
            slots = []
            if remainder > 0:
                # Has remainder: first slot is top with remainder qty
                slots.append({"qty": remainder, "is_top": True, "tray_id": None})
                # Then full capacity trays as non-top
                for i in range(full_trays):
                    slots.append({"qty": capacity, "is_top": False, "tray_id": None})
            else:
                # No remainder: first full capacity tray is top, rest are non-top
                slots.append({"qty": capacity, "is_top": True, "tray_id": None})
                for i in range(full_trays - 1):
                    slots.append({"qty": capacity, "is_top": False, "tray_id": None})
            return slots

        accept_slots = compute_slots(accepted_qty, tray_capacity) if accepted_qty > 0 else []
        reject_slots = compute_slots(rejected_qty, tray_capacity) if rejected_qty > 0 else []
        unmapped_trays = [t for t in active_trays]

        reuse_result = compute_reuse_trays(
            [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t.get("is_top", False)} for t in active_trays],
            rejected_qty
        )

        return JsonResponse({
            "success": True, "lot_id": lot_id,
            "total_qty": total_qty, "tray_capacity": tray_capacity,
            "accepted_qty": accepted_qty, "rejected_qty": rejected_qty,
            "accept_slots": accept_slots, "reject_slots": reject_slots,
            "original_trays": [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t.get("is_top", False)} for t in active_trays],
            "unmapped_trays": [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t.get("is_top", False)} for t in unmapped_trays],
            "reuse_trays": reuse_result["reuse_trays"],
            "reuse_count": len(reuse_result["reuse_trays"]),
            "reuse_updated_trays": reuse_result["updated_trays"],
        })

    elif action == 'VALIDATE_TRAY':
        tray_id = request.data.get('tray_id', '').strip().upper()
        lot_id = request.data.get('lot_id', '').strip()
        if not tray_id:
            return JsonResponse({"valid": False, "error": "tray_id is required"}, status=400)
        
        # ═══ TRAY TYPE COMPATIBILITY CHECK ═══
        def get_tray_category(tray_type_code):
            """Extract category (Jumbo/Normal) from tray type code: J*->Jumbo, N*->Normal"""
            if not tray_type_code:
                return None
            code = str(tray_type_code).upper().strip()
            if code.startswith('J'):
                return 'Jumbo'
            elif code.startswith('N'):
                return 'Normal'
            return None

        try:
            stock = TotalStockModel.objects.select_related('batch_id__model_stock_no').get(lot_id=lot_id)
            # Get model's required tray type from ModelMaster
            model_tray_type = stock.batch_id.model_stock_no.tray_type if stock.batch_id and stock.batch_id.model_stock_no else None
            if model_tray_type:
                model_category = get_tray_category(model_tray_type.tray_type)
            else:
                model_category = None
        except TotalStockModel.DoesNotExist:
            return JsonResponse({"valid": False, "error": "Lot not found"}, status=404)
        
        tray = TrayId.objects.filter(tray_id=tray_id).first()
        if not tray:
            return JsonResponse({"valid": False, "error": "Tray ID not found in system"})
        if tray.lot_id and tray.lot_id != lot_id:
            return JsonResponse({"valid": False, "error": f"Tray belongs to lot {tray.lot_id}"})

        # ═══ BRASS QC REJECTION CHECK ═══
        # A tray rejected during Brass QC must never be scanned/accepted here.
        # Brass QC only records rejected trays inside its submission snapshots
        # (no live rejected_tray flag), so check those snapshots explicitly.
        from Brass_QC.services.validators import validate_tray_not_rejected_in_brass_qc
        brass_qc_reject_error = validate_tray_not_rejected_in_brass_qc(tray_id)
        if brass_qc_reject_error:
            return JsonResponse({"valid": False, "error": brass_qc_reject_error})

        # ═══ TRAY TYPE COMPATIBILITY CHECK ═══
        # Verify scanned tray's type matches model's required type (Jumbo/Normal)
        if model_category:
            tray_category = get_tray_category(tray.tray_type)
            if tray_category and tray_category != model_category:
                return JsonResponse({
                    "valid": False,
                    "error": f"Tray type mismatch: model requires {model_category} tray, but scanned tray is {tray_category}",
                })

        return JsonResponse({"valid": True})

    elif action == 'GET_REASONS':
        reasons = Brass_Audit_Rejection_Table.objects.all().order_by('rejection_reason_id')
        data = [
            {"id": r.id, "reason_id": r.rejection_reason_id, "reason": r.rejection_reason}
            for r in reasons
        ]
        return JsonResponse({"success": True, "reasons": data})

    elif action == 'SAVE_DRAFT':
        lot_id = request.data.get('lot_id')
        draft_payload = request.data.get('draft_data', {})
        if not lot_id:
            return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
        if not draft_payload:
            return JsonResponse({"success": False, "error": "draft_data is required"}, status=400)
        try:
            stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
        except TotalStockModel.DoesNotExist:
            return JsonResponse({"success": False, "error": "Lot not found"}, status=404)
        if stock.brass_audit_hold_lot:
            return JsonResponse({"success": False, "error": "This lot is on hold and cannot be processed until released."}, status=400)
        if Brass_Audit_Submission.objects.filter(lot_id=lot_id, is_completed=True).exists():
            return JsonResponse({"success": False, "error": "Lot already submitted — cannot save draft"}, status=409)
        draft, created = Brass_Audit_Draft_Store.objects.update_or_create(
            lot_id=lot_id,
            draft_type='rejection_draft',
            defaults={
                'batch_id': stock.batch_id.batch_id if stock.batch_id else '',
                'user': request.user,
                'draft_data': draft_payload,
            }
        )
        # Generate transition lot_id for draft
        if not draft.draft_transition_lot_id:
            draft.draft_transition_lot_id = generate_new_lot_id()
            draft.save(update_fields=['draft_transition_lot_id'])
            logger.info(f"[AUDIT DRAFT TRANSITION] lot_id={lot_id} → draft_transition_lot_id={draft.draft_transition_lot_id}")
        stock.brass_audit_draft = True
        stock.brass_audit_onhold_picking = True
        stock.current_stage = 'Brass Audit'
        stock.save(update_fields=['brass_audit_draft', 'brass_audit_onhold_picking', 'current_stage'])
        logger.info(f"[AUDIT DRAFT] Saved for lot_id={lot_id}, user={request.user}")
        return JsonResponse({
            "success": True, "lot_id": lot_id, "draft_id": draft.id,
            "draft_transition_lot_id": draft.draft_transition_lot_id,
            "message": "Draft saved. Lot marked as Draft.",
            "lot_status": "Draft", "action_state": "ONHOLD_TOPTRAY",
        })

    elif action == 'GET_DRAFT':
        lot_id = request.data.get('lot_id')
        if not lot_id:
            return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
        draft = Brass_Audit_Draft_Store.objects.filter(lot_id=lot_id, draft_type='rejection_draft').first()
        if not draft:
            return JsonResponse({"success": True, "has_draft": False, "draft_data": None, "lot_id": lot_id})
        return JsonResponse({
            "success": True, "has_draft": True,
            "draft_data": draft.draft_data, "lot_id": lot_id,
        })

    elif action in ('FULL_ACCEPT', 'FULL_REJECT', 'PARTIAL', 'PROCESS', 'SAVE_REMARK'):
        return _handle_audit_submission(request, action)

    else:
        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)


# ═══════════════════════════════════════════════════════════════
# Submission Handler — Stage Movement for Brass Audit
# ═══════════════════════════════════════════════════════════════
def _handle_audit_submission(request, action):
    data = request.data
    # FIX 1: Accept both lot_id and stock_lot_id — enforce single contract
    lot_id = data.get("lot_id") or data.get("stock_lot_id")
    rejection_reasons = data.get("rejection_reasons", [])
    accepted_tray_ids = data.get("accepted_tray_ids", [])
    rejected_tray_ids = data.get("rejected_tray_ids", [])
    remarks = data.get("remarks", "").strip()

    logger.info(f"[AUDIT ACTION] [INPUT] lot_id={lot_id}, action={action}, user={request.user}")

    if not lot_id:
        return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)

    # Handle SAVE_REMARK separately (no locking needed)
    if action == "SAVE_REMARK":
        try:
            stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
        except TotalStockModel.DoesNotExist:
            return JsonResponse({"success": False, "error": "Lot not found"}, status=404)
        if stock.brass_audit_hold_lot:
            return JsonResponse({"success": False, "error": "This lot is on hold and cannot be processed until released."}, status=400)
        remark_text = remarks
        if not remark_text:
            return JsonResponse({"success": False, "error": "Remark text is required"}, status=400)
        if len(remark_text) > 100:
            return JsonResponse({"success": False, "error": "Remark must be 100 characters or less"}, status=400)
        stock.BA_pick_remarks = remark_text
        stock.save(update_fields=['BA_pick_remarks'])
        return JsonResponse({"success": True, "lot_id": lot_id, "message": "Remark saved successfully", "has_remark": True})

    try:
        stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
    except TotalStockModel.DoesNotExist:
        return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

    if stock.brass_audit_hold_lot:
        return JsonResponse({"success": False, "error": "This lot is on hold and cannot be processed until released."}, status=400)

    existing = Brass_Audit_Submission.objects.filter(
        lot_id=lot_id,
        is_completed=True
    ).order_by('-id').first()

    # ── Re-entry detection ──
    # A lot may return to Brass Audit after the cycle: BA FULL_REJECT → BQC → BA (2nd pass).
    # When that happens an old completed BA submission exists, but the stock flags confirm
    # the current pass has NOT been processed yet (no BA accept / reject / few-cases flag).
    # In that case we allow a fresh submission instead of blocking with "Already submitted".
    is_ba_reentry = (
        existing is not None
        and not stock.brass_audit_accptance
        and not stock.brass_audit_rejection
        and not stock.brass_audit_few_cases_accptance
    )

    if existing and not is_ba_reentry:
        return JsonResponse({
            "success": True,
            "message": "Already submitted",
            "lot_id": lot_id,
            "accept_lot_id": existing.transition_accept_lot_id,
            "reject_lot_id": existing.transition_reject_lot_id,
            "transition_lot_id": existing.transition_lot_id,
        })

    if is_ba_reentry:
        logger.info(
            f"[AUDIT] BA re-entry from BQC detected for lot_id={lot_id} "
            f"(prev submission id={existing.id}, type={existing.submission_type}). "
            f"Allowing fresh BA processing."
        )

    tray_data, source, total_qty = _resolve_lot_trays_audit(lot_id)
    if not tray_data:
        return JsonResponse({"success": False, "error": "No tray data found for this lot"}, status=400)
    if total_qty <= 0:
        return JsonResponse({"success": False, "error": "Total lot quantity is zero"}, status=400)

    active_trays = [t for t in tray_data if not t["is_delinked"]]

    if action == "FULL_ACCEPT":
        submission_type = "FULL_ACCEPT"
        accepted_qty = total_qty
        rejected_qty = 0
        accepted_trays = [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]} for t in active_trays]
        rejected_trays = []

    elif action == "FULL_REJECT":
        submission_type = "FULL_REJECT"
        if rejection_reasons:
            total_reject_from_reasons = sum(int(r.get("qty", 0)) for r in rejection_reasons)
            if total_reject_from_reasons != total_qty:
                logger.warning(f"[AUDIT ACTION] FULL_REJECT reason qty mismatch: reasons={total_reject_from_reasons}, lot={total_qty}")
        accepted_qty = 0
        rejected_qty = total_qty
        accepted_trays = []
        if rejected_tray_ids:
            active_tray_map = {t["tray_id"]: t for t in active_trays}
            rejected_trays = [{"tray_id": tid, "qty": active_tray_map[tid]["qty"], "is_top": active_tray_map[tid]["is_top"]}
                              for tid in rejected_tray_ids if tid in active_tray_map]
        else:
            rejected_trays = [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]} for t in active_trays]

    elif action == "PARTIAL":
        submission_type = "PARTIAL"
        if not rejection_reasons:
            return JsonResponse({"success": False, "error": "Rejection reasons are required for partial reject"}, status=400)
        total_reject_from_reasons = sum(int(r.get("qty", 0)) for r in rejection_reasons)
        if total_reject_from_reasons <= 0:
            return JsonResponse({"success": False, "error": "Rejection qty must be greater than 0"}, status=400)
        if total_reject_from_reasons >= total_qty:
            return JsonResponse({"success": False, "error": "Partial reject qty must be less than total lot qty"}, status=400)
        rejected_qty = total_reject_from_reasons
        accepted_qty = total_qty - rejected_qty

        # BUG 3 — AQL enforcement: if rejection qty exceeds AQL limit, auto-upgrade to FULL_REJECT
        _aql_plan = AQLSamplingPlan.objects.filter(
            lot_qty_from__lte=total_qty,
            lot_qty_to__gte=total_qty
        ).first()
        if _aql_plan and rejected_qty > _aql_plan.aql_limit:
            logger.warning(
                f"[AQL AUTO FULL REJECT] lot_id={lot_id}, total_qty={total_qty}, "
                f"rejected_qty={rejected_qty}, aql_limit={_aql_plan.aql_limit} — upgrading PARTIAL to FULL_REJECT"
            )
            submission_type = "FULL_REJECT"
            accepted_qty = 0
            rejected_qty = total_qty
            accepted_trays = []
            _rich_reject_fr = data.get("rejected_trays", [])
            if _rich_reject_fr:
                rejected_trays = [
                    {"tray_id": str(t.get("tray_id", "")), "qty": int(t.get("qty") or 0),
                     "is_top": bool(t.get("is_top", False))}
                    for t in _rich_reject_fr
                ]
            elif rejected_tray_ids:
                _atm = {t["tray_id"]: t for t in active_trays}
                rejected_trays = [
                    {"tray_id": tid, "qty": _atm[tid]["qty"], "is_top": _atm[tid]["is_top"]}
                    for tid in rejected_tray_ids if tid in _atm
                ] or [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]} for t in active_trays]
            else:
                rejected_trays = [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]} for t in active_trays]
        else:
            rejected_trays = []
            accepted_trays = []
            # BUG 1 — rich tray payload: UI sends exact split quantities per tray
            _rich_accept = data.get("accepted_trays", [])
            _rich_reject = data.get("rejected_trays", [])
            if _rich_accept or _rich_reject:
                # Use exact split quantities from UI payload (handles partial-fill trays)
                accepted_trays = [
                    {"tray_id": str(t.get("tray_id", "")), "qty": int(t.get("qty") or 0),
                     "is_top": bool(t.get("is_top", False))}
                    for t in _rich_accept
                ]
                rejected_trays = [
                    {"tray_id": str(t.get("tray_id", "")), "qty": int(t.get("qty") or 0),
                     "is_top": bool(t.get("is_top", False))}
                    for t in _rich_reject
                ]
                _actual_accept = sum(t["qty"] for t in accepted_trays)
                _actual_reject = sum(t["qty"] for t in rejected_trays)
                if _actual_accept != accepted_qty or _actual_reject != rejected_qty:
                    return JsonResponse({
                        "success": False,
                        "error": (
                            f"Tray qty mismatch: accept {_actual_accept}\u2260{accepted_qty} "
                            f"or reject {_actual_reject}\u2260{rejected_qty}"
                        )
                    }, status=400)
            elif rejected_tray_ids:
                # ID-only fallback: original tray quantities used (no split-tray support)
                active_tray_map = {t["tray_id"]: t for t in active_trays}
                for t in active_trays:
                    if t["tray_id"] in rejected_tray_ids:
                        rejected_trays.append({"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]})
                    else:
                        accepted_trays.append({"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]})
            else:
                remaining_reject = rejected_qty
                sorted_trays = sorted(active_trays, key=lambda t: (not t["is_top"]))
                for t in sorted_trays:
                    if remaining_reject <= 0:
                        accepted_trays.append({"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]})
                    elif remaining_reject >= t["qty"]:
                        rejected_trays.append({"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t["is_top"]})
                        remaining_reject -= t["qty"]
                    else:
                        rejected_trays.append({"tray_id": t["tray_id"], "qty": remaining_reject, "is_top": t["is_top"]})
                        accepted_trays.append({"tray_id": t["tray_id"], "qty": t["qty"] - remaining_reject, "is_top": False})
                        remaining_reject = 0

    elif action == "PROCESS":
        tray_actions = data.get("tray_actions", [])
        if not tray_actions:
            return JsonResponse({"success": False, "error": "tray_actions required for PROCESS action"}, status=400)
        active_tray_map = {t["tray_id"]: t for t in active_trays}
        accepted_trays = []
        rejected_trays = []
        for ta in tray_actions:
            tid = ta.get("tray_id")
            ta_action = ta.get("action")
            is_top = bool(ta.get("is_top", False))
            if ta_action not in ("ACCEPT", "REJECT", "DELINK"):
                return JsonResponse({"success": False, "error": f"Invalid tray action '{ta_action}' for tray {tid}"}, status=400)
            tray_match = active_tray_map.get(tid)
            if not tray_match:
                if ta_action == "REJECT":
                    if not TrayId.objects.filter(tray_id=tid).exists():
                        return JsonResponse({"success": False, "error": f"Reject tray '{tid}' not found in master tray list"}, status=400)
                    slot_qty = int(ta.get("qty") or 0)
                    if slot_qty <= 0:
                        slot_qty = (stock.batch_id.tray_capacity if stock.batch_id else 0) or 0
                    rejected_trays.append({"tray_id": tid, "qty": slot_qty, "is_top": False})
                    continue
                return JsonResponse({"success": False, "error": f"Tray {tid} not found in lot"}, status=400)
            # ✅ FIX: Honour UI-provided qty for REJECT slots (top tray qty is updated by UI
            # when reject qty < parent tray qty). Without this, the parent's original qty
            # is stored for the top reject tray, causing partial_reject_data to show stale qty.
            if ta_action == "REJECT":
                _ui_qty = ta.get("qty")
                _entry_qty = int(_ui_qty) if _ui_qty is not None and int(_ui_qty) > 0 else tray_match["qty"]
                tray_entry = {"tray_id": tid, "qty": _entry_qty, "is_top": is_top}
            else:
                tray_entry = {"tray_id": tid, "qty": tray_match["qty"], "is_top": is_top}
            if ta_action == "ACCEPT":
                accepted_trays.append(tray_entry)
            elif ta_action == "REJECT":
                rejected_trays.append(tray_entry)
            elif ta_action == "DELINK":
                BrassAuditTrayId.objects.filter(lot_id=lot_id, tray_id=tid).update(delink_tray=True)
                TrayId.objects.filter(lot_id=lot_id, tray_id=tid).update(delink_tray=True)

        if accepted_trays:
            top_count = sum(1 for t in accepted_trays if t["is_top"])
            if top_count != 1:
                return JsonResponse({"success": False, "error": f"Exactly one accepted tray must be marked as top (found {top_count})"}, status=400)

        rejected_qty = sum(int(r.get("qty", 0)) for r in rejection_reasons) if rejection_reasons else 0
        accepted_qty = total_qty - rejected_qty
        if rejected_qty < 0 or rejected_qty > total_qty:
            return JsonResponse({"success": False, "error": "Invalid rejection quantity"}, status=400)

        # ── FIX: PROCESS ACCEPT tray_actions carry no qty from UI.
        # When a tray is split (reject portion moved to a new tray), the accepted
        # portion must equal accepted_qty. Reconcile by adjusting the top tray.
        if accepted_trays and accepted_qty > 0:
            _sum_accept = sum(t["qty"] for t in accepted_trays)
            if _sum_accept != accepted_qty:
                _excess = _sum_accept - accepted_qty
                for t in accepted_trays:
                    if t["is_top"] and t["qty"] > _excess:
                        t["qty"] -= _excess
                        logger.info(
                            f"[AUDIT PROCESS] Reconciled top tray {t['tray_id']} qty: "
                            f"{t['qty'] + _excess} → {t['qty']} (accepted_qty={accepted_qty})"
                        )
                        break

        if rejected_qty == 0:
            submission_type = "FULL_ACCEPT"
        elif accepted_qty == 0:
            submission_type = "FULL_REJECT"
        else:
            submission_type = "PARTIAL"
        if rejected_qty > 0 and not rejection_reasons:
            return JsonResponse({"success": False, "error": "Rejection reasons required when rejecting trays"}, status=400)

    # Store rejection reasons
    if rejection_reasons and action in ("FULL_REJECT", "PARTIAL", "PROCESS"):
        try:
            reason_store = Brass_Audit_Rejection_ReasonStore.objects.create(
                lot_id=lot_id, user=request.user, total_rejection_quantity=rejected_qty,
                batch_rejection=(action == "FULL_REJECT"), lot_rejected_comment=remarks or None,
            )
            reason_ids = []
            for r in rejection_reasons:
                reason_id = r.get("reason_id")
                qty = int(r.get("qty", 0))
                if qty > 0 and reason_id:
                    try:
                        reason_obj = Brass_Audit_Rejection_Table.objects.get(id=reason_id)
                        reason_ids.append(reason_obj.id)
                        Brass_Audit_Rejected_TrayScan.objects.create(
                            lot_id=lot_id, rejected_tray_quantity=str(qty), rejected_tray_id=None,
                            rejection_reason=reason_obj, user=request.user,
                        )
                    except Brass_Audit_Rejection_Table.DoesNotExist:
                        logger.warning(f"[AUDIT ACTION] Rejection reason not found: id={reason_id}")
            if reason_ids:
                reason_store.rejection_reason.set(reason_ids)
        except Exception as e:
            logger.error(f"[AUDIT ACTION] Error storing rejection reasons: {e}")

    # Save submission
    accept_snapshot = {"qty": accepted_qty, "trays": accepted_trays} if accepted_trays else None
    reject_snapshot = {"qty": rejected_qty, "trays": rejected_trays} if rejected_trays else None
    submission = Brass_Audit_Submission.objects.create(
        lot_id=lot_id, batch_id=stock.batch_id.batch_id if stock.batch_id else "",
        submission_type=submission_type, total_lot_qty=total_qty,
        accepted_qty=accepted_qty, rejected_qty=rejected_qty,
        full_accept_data=accept_snapshot if submission_type == "FULL_ACCEPT" else None,
        full_reject_data=reject_snapshot if submission_type == "FULL_REJECT" else None,
        partial_accept_data=accept_snapshot if submission_type == "PARTIAL" else None,
        partial_reject_data=reject_snapshot if submission_type == "PARTIAL" else None,
        snapshot_data={
            "lot_qty": total_qty, "accepted": accepted_trays, "rejected": rejected_trays,
            "rejection_reasons": rejection_reasons if rejection_reasons else [], "remarks": remarks,
        },
        is_completed=True, created_by=request.user,
    )

    # ═══ TRANSITION LOT ID — Create new lot_id for each transition ═══
    if submission_type == "FULL_ACCEPT":
        t_lot_id = generate_new_lot_id()
        t_label = "full accept from brass audit to jig loading"
        submission.transition_lot_id = t_lot_id
        submission.transition_label = t_label
        submission.save(update_fields=['transition_lot_id', 'transition_label'])
        stock.brass_audit_transition_lot_id = t_lot_id
        stock.brass_audit_transition_label = t_label
        logger.info(f"[AUDIT TRANSITION] FULL_ACCEPT lot_id={lot_id} → transition_lot_id={t_lot_id}")
    elif submission_type == "FULL_REJECT":
        t_lot_id = generate_new_lot_id()
        t_label = "full reject from brass audit to brass qc"
        submission.transition_lot_id = t_lot_id
        submission.transition_label = t_label
        submission.save(update_fields=['transition_lot_id', 'transition_label'])
        stock.brass_audit_transition_lot_id = t_lot_id
        stock.brass_audit_transition_label = t_label
        logger.info(f"[AUDIT TRANSITION] FULL_REJECT lot_id={lot_id} → transition_lot_id={t_lot_id}")
    elif submission_type == "PARTIAL":
        # ✅ FIX: Use UUID-based lot_id generation to prevent race conditions
        # Old format: LID30042026055925829A/R (vulnerable to collision)
        # New format: LID202604301129450123455a3c / LID202604301129450123457b9d
        import uuid
        now = timezone.now()
        accept_lot_id = f"LID{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}{uuid.uuid4().hex[:4]}"
        reject_lot_id = f"LID{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}{uuid.uuid4().hex[:4]}"

        t_label = "partial: accept child -> Jig Loading | reject child -> IQF"
        submission.transition_accept_lot_id = accept_lot_id
        submission.transition_reject_lot_id = reject_lot_id
        submission.transition_label = t_label
        submission.is_completed = True
        submission.save()

        with transaction.atomic():
            # ── Accepted child lot → Jig Loading ──
            accepted_child = TotalStockModel.objects.get(pk=stock.pk)
            accepted_child.pk = None
            accepted_child.id = None
            accepted_child.lot_id = accept_lot_id
            accepted_child.total_stock = accepted_qty
            # ✅ FIX: Set total_IP_accpeted_quantity to accepted_qty so downstream modules
            # (Jig Loading) display correct qty instead of inherited parent qty.
            accepted_child.total_IP_accpeted_quantity = accepted_qty
            accepted_child.brass_audit_physical_qty = accepted_qty
            accepted_child.brass_audit_accepted_qty = accepted_qty
            # ✅ FIX: Do NOT set brass_qc_* flags on child lots
            # This child belongs to Jig Loading stage, not Brass QC.
            # Setting brass_qc_accptance=True causes it to appear in Brass QC Completed table (wrong stage).
            accepted_child.brass_qc_accepted_qty = 0
            accepted_child.brass_physical_qty = 0
            accepted_child.brass_qc_accptance = False
            accepted_child.brass_qc_accepted_qty_verified = False
            accepted_child.brass_qc_rejection = False
            accepted_child.brass_qc_few_cases_accptance = False
            accepted_child.brass_audit_accptance = True
            accepted_child.brass_audit_few_cases_accptance = False
            accepted_child.brass_audit_rejection = False
            accepted_child.last_process_module = 'Brass Audit'
            accepted_child.next_process_module = 'Jig Loading'
            accepted_child.current_stage = 'Brass Audit'
            accepted_child.send_brass_audit_to_iqf = False
            accepted_child.send_brass_audit_to_qc = False
            accepted_child.brass_audit_draft = False
            accepted_child.brass_audit_onhold_picking = False
            accepted_child.brass_audit_last_process_date_time = timezone.now()
            accepted_child.last_process_date_time = timezone.now()
            accepted_child.save()
            accepted_child.location.set(stock.location.all())

            BrassAuditTrayId.objects.bulk_create([
                BrassAuditTrayId(
                    lot_id=accept_lot_id,
                    tray_id=t["tray_id"],
                    tray_quantity=int(t["qty"]),
                    batch_id=stock.batch_id,
                    user=request.user,
                    top_tray=bool(t.get("is_top", False)),
                    rejected_tray=False,
                    delink_tray=False,
                    new_tray=False
                )
                for t in accepted_trays if int(t.get("qty", 0)) > 0
            ])

            # ── Rejected child lot → IQF ──
            rejected_child = TotalStockModel.objects.get(pk=stock.pk)
            rejected_child.pk = None
            rejected_child.id = None
            rejected_child.lot_id = reject_lot_id
            rejected_child.total_stock = rejected_qty
            # ✅ FIX: Set total_IP_accpeted_quantity to rejected_qty so IQF pick table
            # displays correct qty instead of inherited parent qty.
            rejected_child.total_IP_accpeted_quantity = rejected_qty
            rejected_child.brass_audit_physical_qty = 0
            rejected_child.brass_audit_accepted_qty = 0
            # ✅ FIX: Do NOT set brass_qc_* flags on child lots
            # This child belongs to IQF stage, not Brass QC.
            # Setting brass_qc_accptance=True would cause it to appear in Brass QC Completed table (wrong).
            rejected_child.brass_qc_accepted_qty = 0
            rejected_child.brass_physical_qty = 0
            rejected_child.brass_qc_accptance = False
            rejected_child.brass_qc_accepted_qty_verified = False
            rejected_child.brass_qc_rejection = False
            rejected_child.brass_qc_few_cases_accptance = False
            # ✅ FIX: Route reject child to IQF (Brass Audit partial reject hierarchy)
            # Brass Audit - Partial Reject → reject portion goes to IQF
            rejected_child.brass_audit_rejection = True
            rejected_child.brass_audit_accptance = False
            rejected_child.brass_audit_few_cases_accptance = False
            rejected_child.last_process_module = 'Brass Audit'
            rejected_child.next_process_module = 'IQF'
            rejected_child.current_stage = 'Brass Audit'
            rejected_child.send_brass_audit_to_iqf = True
            rejected_child.send_brass_audit_to_qc = False
            # Set IQF qty — the rejected qty flows into IQF for reprocessing
            rejected_child.iqf_accepted_qty = rejected_qty
            rejected_child.iqf_rejection = False
            rejected_child.iqf_acceptance = False
            rejected_child.iqf_few_cases_acceptance = False
            rejected_child.iqf_onhold_picking = False
            rejected_child.brass_qc_transition_reject_lot_id = None
            rejected_child.brass_qc_transition_accept_lot_id = None
            rejected_child.brass_audit_draft = False
            rejected_child.brass_audit_onhold_picking = False
            rejected_child.brass_audit_last_process_date_time = timezone.now()
            rejected_child.last_process_date_time = timezone.now()
            rejected_child.save()
            rejected_child.location.set(stock.location.all())

            # ✅ FIX: Reject child goes to IQF — create IQFTrayId records.
            # IQF reads tray data from IQFTrayId via its tray resolver.
            # ✅ BUG FIX (Bug 2): Reset IQF verification checkbox to unchecked when lot enters IQF
            rejected_child.iqf_accepted_qty_verified = False
            rejected_child.save(update_fields=['iqf_accepted_qty_verified'])
            
            from IQF.models import IQFTrayId
            IQFTrayId.objects.bulk_create([
                IQFTrayId(
                    lot_id=reject_lot_id,
                    tray_id=t["tray_id"],
                    tray_quantity=int(t["qty"]),
                    batch_id=stock.batch_id,
                    user=request.user,
                    top_tray=bool(t.get("is_top", False)),
                    rejected_tray=False,
                    delink_tray=False,
                    new_tray=False,
                    remaining_qty=int(t["qty"]),
                )
                for t in rejected_trays if int(t.get("qty", 0)) > 0
            ])

            # Rejection reason store for rejected child (Brass QC reads rw_qty from this)
            _rej_store = Brass_Audit_Rejection_ReasonStore.objects.create(
                lot_id=reject_lot_id,
                user=request.user,
                total_rejection_quantity=rejected_qty,
                batch_rejection=False,
            )
            _child_reason_ids = []
            for r in rejection_reasons:
                _rid = r.get("reason_id")
                _rqty = int(r.get("qty", 0))
                if _rqty > 0 and _rid:
                    try:
                        _reason_obj = Brass_Audit_Rejection_Table.objects.get(id=_rid)
                        _child_reason_ids.append(_reason_obj.id)
                        Brass_Audit_Rejected_TrayScan.objects.create(
                            lot_id=reject_lot_id,
                            rejected_tray_quantity=str(_rqty),
                            rejected_tray_id=None,
                            rejection_reason=_reason_obj,
                            user=request.user,
                        )
                    except Brass_Audit_Rejection_Table.DoesNotExist:
                        pass
            if _child_reason_ids:
                _rej_store.rejection_reason.set(_child_reason_ids)

            # ✅ FIX: Create snapshot records in BrassAudit_PartialAcceptLot and BrassAudit_PartialRejectLot
            # These tables store the frozen tray snapshots for accept/reject child lots.
            # View icons and downstream modules read from these tables to get correct lot qty.
            
            # Build rejection reasons dict for BrassAudit_PartialRejectLot
            reasons_dict = {}
            for r in rejection_reasons:
                _rid = r.get("reason_id")
                _rqty = int(r.get("qty", 0))
                if _rqty > 0 and _rid:
                    try:
                        _reason_obj = Brass_Audit_Rejection_Table.objects.get(id=_rid)
                        _rid_code = _reason_obj.rejection_reason_id or f"R{_rid}"
                        reasons_dict[_rid_code] = {
                            "reason": _reason_obj.rejection_reason,
                            "qty": _rqty
                        }
                    except Brass_Audit_Rejection_Table.DoesNotExist:
                        pass
            
            # Create BrassAudit_PartialAcceptLot snapshot
            BrassAudit_PartialAcceptLot.objects.create(
                new_lot_id=accept_lot_id,
                parent_lot_id=stock.lot_id,
                parent_batch_id=stock.batch_id.batch_id if stock.batch_id else '',
                parent_submission=submission,
                accepted_qty=accepted_qty,
                accept_trays_count=len(accepted_trays),
                trays_snapshot=accepted_trays,
                created_by=request.user,
            )
            
            # Create BrassAudit_PartialRejectLot snapshot
            BrassAudit_PartialRejectLot.objects.create(
                new_lot_id=reject_lot_id,
                parent_lot_id=stock.lot_id,
                parent_batch_id=stock.batch_id.batch_id if stock.batch_id else '',
                parent_submission=submission,
                rejected_qty=rejected_qty,
                reject_trays_count=len(rejected_trays),
                rejection_reasons=reasons_dict,
                trays_snapshot=rejected_trays,
                remarks=remarks,
                created_by=request.user,
            )

            logger.info(
                f"[BRASS AUDIT PARTIAL SNAPSHOT] Created snapshot records: "
                f"Accept={accept_lot_id} (qty={accepted_qty}), "
                f"Reject={reject_lot_id} (qty={rejected_qty})"
            )

            # ── Close parent lot fully ──
            # ✅ FIX: Parent must be EXCLUDED from ALL pick tables (Brass QC, IQF, Jig Loading)
            # Only the child lots (accept→Jig Loading, reject→Brass QC) should appear downstream.
            stock.brass_audit_few_cases_accptance = True
            stock.brass_audit_onhold_picking = False
            stock.brass_audit_accptance = False
            stock.brass_audit_rejection = False
            stock.total_stock = 0
            stock.brass_qc_accepted_qty = 0
            stock.brass_audit_transition_accept_lot_id = accept_lot_id
            stock.brass_audit_transition_reject_lot_id = reject_lot_id
            stock.brass_audit_transition_label = t_label
            stock.last_process_module = 'Brass Audit'
            stock.next_process_module = 'Split Completed'
            stock.last_process_date_time = timezone.now()
            stock.brass_audit_last_process_date_time = timezone.now()
            stock.brass_audit_draft = False
            stock.current_stage = 'Brass Audit'
            # Clear ALL routing flags so parent doesn't appear in any downstream pick table
            stock.send_brass_audit_to_iqf = False
            stock.send_brass_audit_to_qc = False  # ✅ Parent must NOT appear in Brass QC
            stock.send_brass_qc = False           # ✅ Parent must NOT appear via IQF reentry
            stock.iqf_onhold_picking = False
            stock.iqf_acceptance = False
            stock.iqf_rejection = False
            stock.iqf_few_cases_acceptance = False
            # ✅ FIX: Do NOT clear brass_qc_accptance/rejection/few_cases here.
            # These are historical Completed-Table flags — clearing them removes the lot
            # from BQC CT (regression: Issues 1 & 3).
            # remove_lot=True is sufficient to prevent re-entry into pick tables.
            stock.brass_qc_accepted_qty_verified = False
            stock.remove_lot = True
            stock.save(update_fields=[
                "brass_audit_few_cases_accptance",
                "brass_audit_onhold_picking",
                "brass_audit_accptance",
                "brass_audit_rejection",
                "total_stock",
                "brass_qc_accepted_qty",
                "last_process_module",
                "next_process_module",
                "brass_audit_last_process_date_time",
                "last_process_date_time",
                "brass_audit_transition_accept_lot_id",
                "brass_audit_transition_reject_lot_id",
                "brass_audit_transition_label",
                "brass_audit_draft",
                "send_brass_audit_to_iqf",
                "send_brass_audit_to_qc",
                "send_brass_qc",
                "iqf_onhold_picking",
                "iqf_acceptance",
                "iqf_rejection",
                "iqf_few_cases_acceptance",
                "brass_qc_accepted_qty_verified",
                "remove_lot",
                "current_stage",
            ])

        _accept_tray_str = [t['tray_id'] + '(' + str(t['qty']) + ')' for t in accepted_trays]
        _reject_tray_str = [t['tray_id'] + '(' + str(t['qty']) + ')' for t in rejected_trays]
        print(f"\n{'='*60}")
        print(f"[BRASS AUDIT PARTIAL SPLIT] Parent Lot: {lot_id}")
        print(f"  Accept Lot ID: {accept_lot_id} → Jig Loading (qty={accepted_qty})")
        print(f"  Reject Lot ID: {reject_lot_id} → IQF (qty={rejected_qty})")
        print(f"  Accept Trays: {_accept_tray_str}")
        print(f"  Reject Trays: {_reject_tray_str}")
        print(f"{'='*60}\n")

        return JsonResponse({
            "success": True,
            "message": "Partial lot submitted successfully",
            "lot_id": lot_id,
            "submission_id": submission.id,
            "submission_type": submission_type,
            "accepted_qty": accepted_qty,
            "rejected_qty": rejected_qty,
            "accepted_lot_id": accept_lot_id,
            "rejected_lot_id": reject_lot_id,
            "transition_accept_lot_id": accept_lot_id,
            "transition_reject_lot_id": reject_lot_id,
            "transition_label": t_label,
        })

    # ═══ STAGE MOVEMENT — Brass Audit hierarchy ═══
    # Full Accept → Jig Loading
    # Full Reject → back to Brass QC (as NEW lot context)
    if submission_type == "FULL_ACCEPT":
        stock.brass_audit_accptance = True
        stock.brass_audit_rejection = False
        stock.brass_audit_few_cases_accptance = False
        stock.brass_audit_physical_qty = accepted_qty
        stock.brass_audit_accepted_qty = accepted_qty
        stock.next_process_module = 'Jig Loading'
        stock.last_process_module = 'Brass Audit'
    elif submission_type == "FULL_REJECT":
        stock.brass_audit_accptance = False
        stock.brass_audit_rejection = True
        stock.brass_audit_few_cases_accptance = False
        stock.brass_audit_physical_qty = 0
        stock.brass_audit_accepted_qty = 0
        stock.next_process_module = 'Brass QC'
        stock.last_process_module = 'Brass Audit'
        stock.send_brass_audit_to_qc = True
        # ✅ BUG FIX (Bug 1): Reset Brass QC verification checkbox when lot re-enters Brass QC
        # When lot moves from Brass Audit → Brass QC, user must manually verify qty again
        # Previous checked state must NOT carry forward on re-entry
        stock.brass_qc_accepted_qty_verified = False
        # ✅ FIX: DO NOT reset other Brass QC flags — they are historical records
        # The lot will appear in BOTH:
        # - Brass QC Complete table (historical record preserved)
        # - Brass QC Pick table (via send_brass_audit_to_qc=True)
        # This allows reprocessing without losing history

    # Clear draft state
    Brass_Audit_Draft_Store.objects.filter(lot_id=lot_id, draft_type='rejection_draft').delete()
    stock.brass_audit_draft = False
    stock.brass_audit_onhold_picking = False

    stock.last_process_date_time = timezone.now()
    stock.brass_audit_last_process_date_time = timezone.now()
    stock.current_stage = 'Brass Audit'
    stock.save(update_fields=[
        'brass_audit_accptance', 'brass_audit_rejection', 'brass_audit_few_cases_accptance',
        'brass_audit_physical_qty', 'brass_audit_accepted_qty', 'next_process_module', 'last_process_module',
        'last_process_date_time', 'brass_audit_last_process_date_time',
        'brass_audit_draft', 'brass_audit_onhold_picking',
        'send_brass_audit_to_qc', 'send_brass_audit_to_iqf',
        'brass_audit_transition_lot_id', 'brass_audit_transition_label',
        'brass_qc_accepted_qty_verified',
        'current_stage',
    ])

    # Sync accepted trays to BrassAuditTrayId for FULL_ACCEPT only.
    if submission_type == "FULL_ACCEPT" and accepted_trays:
        try:
            BrassAuditTrayId.objects.filter(lot_id=lot_id).delete()
            for t in accepted_trays:
                BrassAuditTrayId.objects.create(
                    lot_id=lot_id,
                    tray_id=t.get("tray_id", ""),
                    tray_quantity=int(t.get("qty") or 0),
                    top_tray=bool(t.get("is_top", False)),
                    delink_tray=False,
                    rejected_tray=False,
                )
            logger.info(f"[AUDIT TRAY SYNC] lot_id={lot_id}, stored {len(accepted_trays)} accepted tray(s) to BrassAuditTrayId")
        except Exception as _e:
            logger.error(f"[AUDIT TRAY SYNC] Failed to sync trays for lot_id={lot_id}: {_e}")

    logger.info(f"[AUDIT ACTION] [DONE] type={submission_type}, lot_id={lot_id}, moved_to={stock.next_process_module}")

    return JsonResponse({
        "success": True,
        "message": f"Lot {submission_type.replace('_', ' ').lower()} and moved to {stock.next_process_module}",
        "lot_id": lot_id, "submission_id": submission.id, "submission_type": submission_type,
        "accepted_qty": accepted_qty, "rejected_qty": rejected_qty,
        "status": f"MOVED_TO_{stock.next_process_module.upper().replace(' ', '_')}",
        "trays": accepted_trays if submission_type != "FULL_REJECT" else rejected_trays,
        "transition_lot_id": submission.transition_lot_id,
        "transition_accept_lot_id": submission.transition_accept_lot_id,
        "transition_reject_lot_id": submission.transition_reject_lot_id,
        "transition_label": submission.transition_label,
    })


# ═══════════════════════════════════════════════════════════════
# Legacy Endpoints — Backward Compatible
# ═══════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_audit_tray_details(request):
    lot_id = request.GET.get('lot_id')
    if not lot_id:
        return JsonResponse({"error": "lot_id is required"}, status=400)
    try:
        stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
    except TotalStockModel.DoesNotExist:
        return JsonResponse({"error": "Lot not found"}, status=404)

    tray_data, source, total_qty = _resolve_lot_trays_audit(lot_id)
    tray_capacity = stock.batch_id.tray_capacity or 0 if stock.batch_id else 0

    return JsonResponse({
        "lot_id": lot_id,
        "batch_id": stock.batch_id.batch_id if stock.batch_id else "",
        "total_qty": total_qty,
        "tray_capacity": tray_capacity,
        "source": source,
        "trays": tray_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def validate_audit_tray_id(request):
    tray_id = request.GET.get('tray_id', '').strip()
    lot_id = request.GET.get('lot_id', '').strip()
    if not tray_id:
        return JsonResponse({"valid": False, "error": "tray_id is required"}, status=400)
    tray = TrayId.objects.filter(tray_id=tray_id).first()
    if not tray:
        return JsonResponse({"valid": False, "error": "Tray ID not found in system"})
    if tray.lot_id and tray.lot_id != lot_id:
        return JsonResponse({"valid": False, "error": f"Tray belongs to lot {tray.lot_id}"})

    from Brass_QC.services.validators import validate_tray_not_rejected_in_brass_qc
    brass_qc_reject_error = validate_tray_not_rejected_in_brass_qc(tray_id)
    if brass_qc_reject_error:
        return JsonResponse({"valid": False, "error": brass_qc_reject_error})

    return JsonResponse({"valid": True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def allocate_audit_trays(request):
    lot_id = request.data.get('lot_id')
    rejected_qty = int(request.data.get('rejected_qty', 0))
    if not lot_id:
        return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
    try:
        stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
    except TotalStockModel.DoesNotExist:
        return JsonResponse({"success": False, "error": "Lot not found"}, status=404)

    tray_data, source, total_qty = _resolve_lot_trays_audit(lot_id)
    active_trays = [t for t in tray_data if not t.get('is_delinked')]
    tray_capacity = stock.batch_id.tray_capacity or 0 if stock.batch_id else 0

    if rejected_qty < 0 or rejected_qty > total_qty:
        return JsonResponse({"success": False, "error": "Invalid rejected_qty"}, status=400)
    accepted_qty = total_qty - rejected_qty

    def compute_slots(qty, capacity):
        if qty <= 0 or capacity <= 0:
            return []
        full_trays = qty // capacity
        remainder = qty % capacity
        slots = []
        if remainder > 0:
            slots.append({"qty": remainder, "is_top": True, "tray_id": None})
        for i in range(full_trays):
            slots.append({"qty": capacity, "is_top": False, "tray_id": None})
        return slots

    accept_slots = compute_slots(accepted_qty, tray_capacity) if accepted_qty > 0 else []
    reject_slots = compute_slots(rejected_qty, tray_capacity) if rejected_qty > 0 else []
    unmapped_trays = [t for t in active_trays]

    return JsonResponse({
        "success": True, "lot_id": lot_id,
        "total_qty": total_qty, "tray_capacity": tray_capacity,
        "accepted_qty": accepted_qty, "rejected_qty": rejected_qty,
        "accept_slots": accept_slots, "reject_slots": reject_slots,
        "original_trays": [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t.get("is_top", False)} for t in active_trays],
        "unmapped_trays": [{"tray_id": t["tray_id"], "qty": t["qty"], "is_top": t.get("is_top", False)} for t in unmapped_trays],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_brass_audit(request):
    data = request.data
    lot_id = data.get("lot_id")
    action = data.get("action", "FULL_ACCEPT")
    if not lot_id:
        return JsonResponse({"success": False, "error": "lot_id is required"}, status=400)
    if action not in ("FULL_ACCEPT", "FULL_REJECT", "PARTIAL", "SAVE_REMARK", "PROCESS"):
        return JsonResponse({"success": False, "error": f"Invalid action: {action}"}, status=400)
    # Delegate to unified handler
    return _handle_audit_submission(request, action)


# ═══════════════════════════════════════════════════════════════
# Raw Submission API — stores exact UI payload
# ═══════════════════════════════════════════════════════════════
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brass_audit_raw_submission(request):
    data = request.data
    lot_id = data.get("lot_id", "").strip()
    batch_id = data.get("batch_id", "").strip()
    plating_stk_no = data.get("plating_stk_no", "").strip()
    submission_type = data.get("submission_type", "DRAFT").upper()

    logger.info(f"[AUDIT RAW] [INPUT] lot_id={lot_id}, type={submission_type}, user={request.user}")

    if not lot_id:
        return JsonResponse({"status": "error", "message": "lot_id is required"}, status=400)
    if submission_type not in ("DRAFT", "SUBMIT"):
        return JsonResponse({"status": "error", "message": f"Invalid submission_type: {submission_type}"}, status=400)

    try:
        stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
    except TotalStockModel.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Lot not found"}, status=404)

    if submission_type == "SUBMIT":
        total_lot_qty = data.get("total_lot_qty", 0)
        summary = data.get("summary", {})
        accepted = summary.get("accepted", 0)
        rejected = summary.get("rejected", 0)
        remarks = data.get("remarks", "").strip()

        if accepted + rejected != total_lot_qty:
            msg = f"Sum check failed: {accepted} + {rejected} != {total_lot_qty}"
            return JsonResponse({"status": "error", "message": msg}, status=400)

        accept_trays = data.get("accept_trays", [])
        accept_top_count = sum(1 for t in accept_trays if t.get("is_top", False))
        if accept_top_count != 1 and len(accept_trays) > 0:
            return JsonResponse({"status": "error", "message": f"Accept must have exactly ONE top tray (found {accept_top_count})"}, status=400)

        reject_trays = data.get("reject_trays", [])
        if rejected > 0:
            reject_top_count = sum(1 for t in reject_trays if t.get("is_top", False))
            if reject_top_count > 1:
                return JsonResponse({"status": "error", "message": f"Reject cannot have more than ONE top tray (found {reject_top_count})"}, status=400)
            if rejected == total_lot_qty and not remarks:
                return JsonResponse({"status": "error", "message": "Remarks are mandatory for full rejection"}, status=400)

    # Auto-create trays if not in master
    all_trays_to_check = data.get("accept_trays", []) + data.get("reject_trays", []) + data.get("delink_trays", [])
    created_trays = []
    for tray in all_trays_to_check:
        tray_id_val = tray.get("tray_id", "").strip()
        if not tray_id_val:
            continue
        existing = TrayId.objects.filter(tray_id=tray_id_val).first()
        if not existing:
            try:
                TrayId.objects.create(
                    lot_id=lot_id, tray_id=tray_id_val,
                    tray_quantity=tray.get("qty", 0),
                    top_tray=tray.get("is_top", False),
                    delink_tray=tray_id_val in [d.get("tray_id", "") for d in data.get("delink_trays", [])]
                )
                created_trays.append({"tray_id": tray_id_val, "qty": tray.get("qty", 0), "is_top": tray.get("is_top", False)})
            except Exception as e:
                logger.error(f"[AUDIT RAW] Error creating tray {tray_id_val}: {e}")

    try:
        raw_submission = Brass_Audit_RawSubmission.objects.create(
            lot_id=lot_id, batch_id=batch_id, plating_stk_no=plating_stk_no,
            payload=data, submission_type=submission_type, created_by=request.user
        )
        return JsonResponse({
            "status": "success", "submission_type": submission_type,
            "lot_id": lot_id, "message": f"Saved successfully ({submission_type})",
            "submission_id": raw_submission.id, "created_trays": created_trays
        })
    except Exception as e:
        logger.error(f"[AUDIT RAW] Error saving: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": 'Unable to process the request. Please verify the submitted data and try again.'}, status=500)


# ═══════════════════════════════════════════════════════════════
# Rejection Details API (for Completed/Reject table view icons)
# ═══════════════════════════════════════════════════════════════
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brass_get_rejection_details(request):
    lot_id = request.GET.get('lot_id')
    if not lot_id:
        return Response({'success': False, 'error': 'Missing lot_id'}, status=400)
    try:
        reason_store = Brass_Audit_Rejection_ReasonStore.objects.filter(lot_id=lot_id).order_by('-id').first()
        if not reason_store:
            return Response({'success': True, 'reasons': []})

        reasons = reason_store.rejection_reason.all()
        total_qty = reason_store.total_rejection_quantity

        if reason_store.batch_rejection:
            if reasons.exists():
                data = [{'reason': r.rejection_reason, 'qty': total_qty} for r in reasons]
            else:
                data = [{'reason': 'Batch rejection: No individual reasons recorded', 'qty': total_qty}]
        else:
            data = [{'reason': r.rejection_reason, 'qty': total_qty} for r in reasons]

        return Response({'success': True, 'reasons': data})
    except Exception as e:
        traceback.print_exc()
        return Response({'success': False, 'error': 'Unable to process the request. Please verify the submitted data and try again.'}, status=500)


# ═══════════════════════════════════════════════════════════════
# Tray Details for Modal (Completed/Reject table view icons)
# ═══════════════════════════════════════════════════════════════
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_brass_audit_tray_details_for_modal(request):
    lot_id = request.GET.get('lot_id')
    if not lot_id:
        return Response({'success': False, 'error': 'Missing lot_id'})

    try:
        stock_obj = TotalStockModel.objects.filter(lot_id=lot_id).first()
        if not stock_obj:
            return Response({'success': False, 'error': 'Lot not found'})

        accepted_trays = []
        rejected_trays = []
        total_accepted_qty = 0

        # Try submission data first
        submission = Brass_Audit_Submission.objects.filter(lot_id=lot_id, is_completed=True).order_by('-created_at').first()
        if submission:
            accept_data = submission.full_accept_data or submission.partial_accept_data or {}
            reject_data = submission.full_reject_data or submission.partial_reject_data or {}
            for t in (accept_data.get('trays') or []):
                qty = int(t.get('qty', 0))
                accepted_trays.append({
                    'tray_id': t.get('tray_id', ''),
                    'tray_quantity': qty,
                    'top_tray': t.get('is_top', False),
                })
                total_accepted_qty += qty
            for t in (reject_data.get('trays') or []):
                rejected_trays.append({
                    'tray_id': t.get('tray_id', ''),
                    'tray_quantity': int(t.get('qty', 0)),
                    'rejection_reason': 'Rejected',
                })
        else:
            # Fallback to BrassAuditTrayId
            trays = BrassAuditTrayId.objects.filter(lot_id=lot_id).order_by('-top_tray', 'tray_quantity')
            for tray in trays:
                if tray.rejected_tray:
                    rejected_trays.append({
                        'tray_id': tray.tray_id,
                        'tray_quantity': tray.tray_quantity or 0,
                        'rejection_reason': 'Rejected',
                    })
                else:
                    accepted_trays.append({
                        'tray_id': tray.tray_id,
                        'tray_quantity': tray.tray_quantity or 0,
                        'top_tray': tray.top_tray,
                    })
                    total_accepted_qty += tray.tray_quantity or 0

            if not trays.exists():
                # Fallback 1: TrayId
                tray_objs = TrayId.objects.filter(lot_id=lot_id)
                brass_trays = {t.tray_id: t for t in BrassTrayId.objects.filter(lot_id=lot_id)}
                for tray in tray_objs:
                    brass_tray = brass_trays.get(tray.tray_id)
                    qty = brass_tray.tray_quantity if brass_tray else tray.tray_capacity or 12
                    top_tray = brass_tray.top_tray if brass_tray else False
                    accepted_trays.append({
                        'tray_id': tray.tray_id,
                        'tray_quantity': qty,
                        'top_tray': top_tray,
                    })
                    total_accepted_qty += qty

                # Fallback 2: IQFTrayId — IQF-accepted child lots store trays here
                if not tray_objs.exists():
                    iqf_trays = IQFTrayId.objects.filter(lot_id=lot_id, delink_tray=False, rejected_tray=False).order_by('-top_tray', 'tray_id')
                    for tray in iqf_trays:
                        qty = int(tray.remaining_qty or 0) if (tray.remaining_qty or 0) > 0 else int(tray.tray_quantity or 0)
                        accepted_trays.append({
                            'tray_id': tray.tray_id,
                            'tray_quantity': qty,
                            'top_tray': bool(tray.top_tray),
                        })
                        total_accepted_qty += qty

                    # Fallback 3: IQF_PartialAcceptLot snapshot — guaranteed to be correct
                    if not iqf_trays.exists():
                        pal = IQF_PartialAcceptLot.objects.filter(new_lot_id=lot_id).first()
                        if pal and pal.trays_snapshot:
                            for t in pal.trays_snapshot:
                                qty = int(t.get('qty', 0))
                                accepted_trays.append({
                                    'tray_id': t.get('tray_id', ''),
                                    'tray_quantity': qty,
                                    'top_tray': bool(t.get('top_tray', False)),
                                })
                                total_accepted_qty += qty

        # Sort: top tray first, then by qty
        accepted_trays.sort(key=lambda x: (not x.get('top_tray', False), x.get('tray_quantity', 0)))

        for idx, tray in enumerate(accepted_trays, 1):
            tray['s_no'] = idx
            if tray.get('top_tray'):
                tray['s_no_display'] = f"{idx} (Top Tray)"
            else:
                tray['s_no_display'] = str(idx)

        _sub_total_qty = submission.total_lot_qty if submission else total_accepted_qty
        _sub_accepted_qty = submission.accepted_qty if submission else total_accepted_qty
        _sub_rejected_qty = submission.rejected_qty if submission else 0
        _sub_type = submission.submission_type if submission else ''
        return Response({
            'success': True,
            'lot_id': lot_id,
            'model_no': (
                stock_obj.batch_id.model_stock_no.model_no
                if stock_obj.batch_id and stock_obj.batch_id.model_stock_no else ''
            ),
            'lot_qty': _sub_total_qty,
            'accepted_qty': _sub_accepted_qty,
            'rejected_qty': _sub_rejected_qty,
            'submission_type': _sub_type,
            'accepted_trays': accepted_trays,
            'rejected_trays': rejected_trays,
            'total_accepted_qty': total_accepted_qty,
        })

    except Exception as e:
        return Response({'success': False, 'error': 'Unable to process the request. Please verify the submitted data and try again.'})


# ═══════════════════════════════════════════════════════════════
# Completed Table - Tray List APIs
# ═══════════════════════════════════════════════════════════════
@method_decorator(csrf_exempt, name='dispatch')
class RejectTableTrayIdListAPIView(APIView):
    def get(self, request):
        lot_id = request.GET.get("lot_id")
        if not lot_id:
            return Response({"success": False, "error": "Lot ID is required"}, status=400)

        try:
            all_trays = []
            is_lot_rejection = False
            lot_rejection_comment = ''

            # ✅ FIX ERR 2: Use submission data as authoritative source for rejected trays
            submission = Brass_Audit_Submission.objects.filter(
                lot_id=lot_id, is_completed=True
            ).order_by('-created_at').first()

            if submission and submission.rejected_qty > 0:
                # Extract rejected trays from submission data
                rejected_data = submission.partial_reject_data or submission.full_reject_data or {}
                rejected_trays_list = rejected_data.get('trays', [])

                for tray in rejected_trays_list:
                    tray_data = {
                        "tray_id": tray.get('tray_id'),
                        "tray_quantity": tray.get('qty', 0),
                        "rejected_tray": True,
                        "delink_tray": tray.get('is_delinked', False),
                        "source": "submission_data",
                    }
                    all_trays.append(tray_data)
                logger.info(f"[RejectTable] Lot {lot_id}: Fetched {len(all_trays)} rejected trays from submission")
            else:
                # Fallback to database queries if submission not found
                main_trays = TrayId.objects.filter(lot_id=lot_id, brass_rejected_tray=True)
                brass_audit_trays = BrassAuditTrayId.objects.filter(lot_id=lot_id, rejected_tray=True)

                for tray in main_trays:
                    tray_data = {
                        "tray_id": tray.tray_id,
                        "tray_quantity": tray.tray_quantity,
                        "rejected_tray": True,
                        "delink_tray": getattr(tray, 'delink_tray', False),
                        "source": "main_table",
                    }
                    all_trays.append(tray_data)

                for tray in brass_audit_trays:
                    exists_in_main = any(t['tray_id'] == tray.tray_id for t in all_trays)
                    if not exists_in_main:
                        tray_data = {
                            "tray_id": tray.tray_id,
                            "tray_quantity": tray.tray_quantity,
                            "rejected_tray": tray.rejected_tray,
                            "delink_tray": getattr(tray, 'delink_tray', False),
                            "source": "brass_audit_table",
                        }
                        all_trays.append(tray_data)

            # Fetch rejection reasons and remarks
            reason_store = Brass_Audit_Rejection_ReasonStore.objects.filter(lot_id=lot_id).order_by('-id').first()
            if reason_store:
                is_lot_rejection = reason_store.batch_rejection
                lot_rejection_comment = reason_store.lot_rejected_comment or ''

            return Response({
                "success": True,
                "trays": all_trays,
                "total_trays": len(all_trays),
                "is_lot_rejection": is_lot_rejection,
                "lot_rejection_comment": lot_rejection_comment,
            })
        except Exception as e:
            logger.error(f"[RejectTable] Error fetching trays for lot {lot_id}: {e}")
            traceback.print_exc()
            return Response({"success": False, "error": 'Unable to process the request. Please verify the submitted data and try again.'}, status=500)


# ═══════════════════════════════════════════════════════════════
# Accepted Tray Scan Data API — for Jig Loading view icon
# ═══════════════════════════════════════════════════════════════
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brass_audit_get_accepted_tray_scan_data(request):
    """Return lot metadata for the Jig Loading view icon panel.

    Returns lot_qty, model_no, plating_stk_no, tray_capacity and available_qty
    so the right-side slide panel can display correct header info.
    """
    lot_id = request.GET.get('lot_id', '').strip()
    if not lot_id:
        return JsonResponse({'success': False, 'error': 'Missing lot_id'}, status=400)

    try:
        stock = TotalStockModel.objects.select_related(
            'model_stock_no', 'batch_id'
        ).filter(lot_id=lot_id).first()

        if not stock:
            return JsonResponse({'success': False, 'error': 'Stock not found'}, status=404)

        model_no = stock.model_stock_no.model_no if stock.model_stock_no else ''

        # plating_stk_no lives on ModelMasterCreation (batch) first, then ModelMaster
        plating_stk_no = ''
        if stock.batch_id and stock.batch_id.plating_stk_no:
            plating_stk_no = stock.batch_id.plating_stk_no
        elif stock.model_stock_no and stock.model_stock_no.plating_stk_no:
            plating_stk_no = stock.model_stock_no.plating_stk_no

        tray_capacity = (
            stock.batch_id.tray_capacity
            if stock.batch_id and stock.batch_id.tray_capacity
            else 10
        )

        brass_audit_physical_qty = stock.brass_audit_physical_qty or 0
        brass_audit_accepted_qty = stock.brass_audit_accepted_qty or 0

        # Prefer the accepted qty; fall back to physical qty if acceptance not yet recorded
        available_qty = brass_audit_accepted_qty if brass_audit_accepted_qty > 0 else brass_audit_physical_qty

        return JsonResponse({
            'success': True,
            'lot_qty': brass_audit_physical_qty,
            'available_qty': available_qty,
            'brass_audit_physical_qty': brass_audit_physical_qty,
            'brass_audit_accepted_qty': brass_audit_accepted_qty,
            'model_no': model_no,
            'plating_stk_no': plating_stk_no,
            'tray_capacity': tray_capacity,
        })
    except Exception as e:
        logger.error(f"[brass_audit_get_accepted_tray_scan_data] Error: {e}")
        return JsonResponse({'success': False, 'error': 'Unable to process the request. Please verify the submitted data and try again.'}, status=500)


# ═══════════════════════════════════════════════════════════════
# Barcode Scanner API
# ═══════════════════════════════════════════════════════════════
def generate_new_lot_id():
    from datetime import datetime as dt
    timestamp = dt.now().strftime("%d%m%Y%H%M%S")
    next_seq_no = 1
    # Iterate recent lots to find last sequential (non-UUID) lot ID
    for lot in TotalStockModel.objects.order_by('-id')[:20]:
        if lot.lot_id and lot.lot_id.startswith("LID"):
            try:
                last_seq_no = int(lot.lot_id[-4:])
                next_seq_no = last_seq_no + 1
                break
            except ValueError:
                continue
    seq_no = f"{next_seq_no:04d}"
    return f"LID{timestamp}{seq_no}"


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lot_id_for_tray(request):
    tray_id = request.GET.get('tray_id', '').strip()
    if not tray_id:
        return JsonResponse({'success': False, 'error': 'tray_id parameter is required'})
    try:
        # Primary: BrassAuditTrayId
        audit_tray = BrassAuditTrayId.objects.filter(tray_id=tray_id).first()
        if audit_tray and audit_tray.lot_id:
            return JsonResponse({'success': True, 'lot_id': str(audit_tray.lot_id), 'source': 'BrassAuditTrayId'})

        # Fallback: BrassTrayId
        brass_tray = BrassTrayId.objects.filter(tray_id=tray_id).first()
        if brass_tray and brass_tray.lot_id:
            return JsonResponse({'success': True, 'lot_id': str(brass_tray.lot_id), 'source': 'BrassTrayId'})

        # Fallback: TrayId
        tray_obj = TrayId.objects.filter(tray_id=tray_id).first()
        if tray_obj and tray_obj.lot_id:
            return JsonResponse({'success': True, 'lot_id': str(tray_obj.lot_id), 'source': 'TrayId'})

        return JsonResponse({'success': False, 'error': f'Tray {tray_id} not found in system'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Unable to process the request. Please verify the submitted data and try again.'})