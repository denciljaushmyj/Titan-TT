from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer
from django.shortcuts import render
from django.db.models import OuterRef, Subquery, Exists, F
from django.core.paginator import Paginator
from django.templatetags.static import static
import math
from modelmasterapp.models import *
from DayPlanning.models import *
from InputScreening.models import *
from Brass_QC.models import *
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import traceback
import logging
from rest_framework import status
from django.http import JsonResponse
import json
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.http import require_GET
from math import ceil
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from IQF.models import *
from BrassAudit.models import *
from Nickel_Audit.models import *
from Nickel_Inspection.models import *
from Jig_Unloading.models import *
from Jig_Unloading.tray_utils import get_upstream_tray_distribution, get_model_master_tray_info
from Inprocess_Inspection.models import InprocessInspectionTrayCapacity
from django.contrib.auth.decorators import login_required
from Nickel_Audit.views import (
    _na_completed_lot_totals, _na_partial_accept_child_maps, _na_unique_completed_rows,
    _na_completed_event_rows, _na_fresh_nw_reacceptance_q,
)
from modelmasterapp.type_of_input import get_type_of_input_map

logger = logging.getLogger(__name__)

def _sort_images_front_first_safe(images):
    """
    Sort model images with Front View first when the optional helper exists.
    Fall back to the original queryset/list order when it is not deployed.
    """
    try:
        from modelmasterapp.image_utils import sort_images_front_first
    except ImportError:
        logger.warning(
            "modelmasterapp.image_utils is unavailable; using default image order"
        )
        return images
    return sort_images_front_first(images)




def _get_input_source(jig_unload_obj):
    """Return location names with fallback chain: M2M → TotalStockModel → TrayId → ModelMasterCreation."""
    names = [loc.location_name for loc in jig_unload_obj.location.all()]
    if not names:
        for raw_cid in (jig_unload_obj.combine_lot_ids or []):
            # combine_lot_ids entries are formatted "-LIDxxx" or "JLOT-xxx-LIDxxx" — extract plain lot_id
            cid = raw_cid.rsplit('-', 1)[-1] if raw_cid and '-' in raw_cid else raw_cid
            if not cid:
                continue
            # Try TotalStockModel first
            tsm = TotalStockModel.objects.filter(lot_id=cid).prefetch_related('location').select_related('batch_id__location').first()
            if tsm and tsm.location.exists():
                names = [loc.location_name for loc in tsm.location.all()]
                break
            if tsm and tsm.batch_id and tsm.batch_id.location:
                names = [tsm.batch_id.location.location_name]
                break
            # Fallback: LID... lot_ids belong to TrayId — trace TrayId.batch_id.location
            tray = TrayId.objects.filter(lot_id=cid).select_related('batch_id__location').first()
            if tray and tray.batch_id and tray.batch_id.location:
                names = [tray.batch_id.location.location_name]
                break
    return ', '.join(names)


def _normalize_source_lot_id(raw_lot_id):
    lot_id = str(raw_lot_id or '').strip()
    if '-' in lot_id:
        return lot_id.rsplit('-', 1)[-1]
    return lot_id


def _source_lot_ids(jig_unload_obj):
    source_lots = []
    for raw_lot_id in jig_unload_obj.combine_lot_ids or []:
        lot_id = _normalize_source_lot_id(raw_lot_id)
        if lot_id:
            source_lots.append(lot_id)
    return source_lots or [jig_unload_obj.lot_id]


def _unique_pick_rows_by_source_lot(queryset):
    seen_source_lots = set()
    unique_rows = []
    for jig_unload_obj in queryset:
        source_lots = _source_lot_ids(jig_unload_obj)
        if any(lot_id in seen_source_lots for lot_id in source_lots):
            continue
        unique_rows.append(jig_unload_obj)
        seen_source_lots.update(source_lots)
    return unique_rows


def _na_tray_capacity(tray_type_name):
    if not tray_type_name:
        return 0
    name = tray_type_name.strip().lower()
    if name.startswith('nr') or name.startswith('nb') or name.startswith('nd') or name in ['normal', 'normal tray']:
        return 20
    if name.startswith('jb') or 'jumbo' in name:
        return 12
    custom = InprocessInspectionTrayCapacity.objects.filter(
        tray_type__tray_type__iexact=tray_type_name, is_active=True
    ).first()
    if custom:
        return custom.custom_capacity
    tt = TrayType.objects.filter(tray_type__iexact=tray_type_name).first()
    return tt.tray_capacity if tt else 0


def _na_effective_qc_rejection(jig_unload_obj):
    """
    na_qc_rejection stays True permanently once a lot is rejected —
    Nickel_Audit._na_do_submit_full_reject routes the same row back to
    Nickel Wiping for rework without clearing it (it's NA's own flag, not
    NW's to reset). Once Nickel Wiping has genuinely re-accepted the lot for
    a fresh audit cycle, the stale flag no longer reflects this cycle's
    status. Mirrors the pick-table queryset carve-out below (and
    Nickel_Audit._na_fresh_nw_reacceptance_q) so the Action column isn't
    disabled for a legitimately re-entered lot.
    """
    return bool(
        jig_unload_obj.na_qc_rejection
        and not (
            jig_unload_obj.nq_qc_accptance
            and jig_unload_obj.nq_last_process_date_time
            and jig_unload_obj.na_last_process_date_time
            and jig_unload_obj.nq_last_process_date_time > jig_unload_obj.na_last_process_date_time
        )
    )


def _na_completed_filter_q():
    return (
        Q(na_qc_accptance=True)
        | Q(na_qc_rejection=True)
        | Q(na_qc_few_cases_accptance=True, na_onhold_picking=False)
    )


def _na_completed_source_lot_ids(allowed_color_ids):
    completed_sources = set()
    completed_rows = (
        JigUnloadAfterTable.objects.filter(
            total_case_qty__gt=0,
            plating_color_id__in=allowed_color_ids,
        )
        .filter(_na_completed_filter_q())
        # A Full Reject from Audit (Nickel_Audit.views._na_do_submit_full_reject,
        # shared by this zone's action API) routes the lot back to Nickel
        # Wiping for rework, while na_qc_rejection is left permanently True
        # as a historical marker. Without this exclusion that stale flag
        # keeps the lot's original source id blacklisted here forever, hiding
        # any later Nickel Wiping resubmission (fresh partial-accept child) for
        # the same source lot from this pick table. See
        # Nickel_Audit._na_fresh_nw_reacceptance_q for why this uses a
        # timestamp comparison instead of current_stage.
        .exclude(_na_fresh_nw_reacceptance_q())
        .only('lot_id', 'combine_lot_ids', 'current_stage')
    )
    for completed_row in completed_rows:
        completed_sources.update(_source_lot_ids(completed_row))
    return completed_sources


def _active_audit_zone_pick_rows(queryset, completed_source_lots):
    rows = list(queryset)
    partial_parent_lots, partial_child_meta = _na_partial_accept_child_maps(rows)
    active_rows = []
    seen_source_lots = set()
    input_count = 0
    direct_submission_excluded = 0
    partial_parent_excluded = 0
    completed_source_excluded = 0
    duplicate_source_excluded = 0

    for jig_unload_obj in rows:
        input_count += 1
        lot_id = str(jig_unload_obj.lot_id or '').strip()
        if lot_id in partial_parent_lots and lot_id not in partial_child_meta:
            partial_parent_excluded += 1
            logger.info(
                "[AUDIT_PICKTABLE_FILTER] zone=Z2 exclude lot=%s reason=partial_parent_child_visible",
                lot_id,
            )
            continue

        child_meta = partial_child_meta.get(lot_id)
        if child_meta:
            jig_unload_obj.nq_partial_parent_lot_id = child_meta.get('parent_lot_id') or ''
            jig_unload_obj.nq_partial_accept_qty = child_meta.get('accepted_qty') or jig_unload_obj.total_case_qty

        source_lots = _source_lot_ids(jig_unload_obj)
        if getattr(jig_unload_obj, 'has_submission', False):
            direct_submission_excluded += 1
            logger.info(
                "[AUDIT_PICKTABLE_FILTER] zone=Z2 exclude lot=%s sources=%s reason=direct_submission",
                jig_unload_obj.lot_id,
                source_lots,
            )
            continue
        if any(lot_id in completed_source_lots for lot_id in source_lots):
            completed_source_excluded += 1
            logger.info(
                "[AUDIT_PICKTABLE_FILTER] zone=Z2 exclude lot=%s sources=%s reason=completed_source",
                jig_unload_obj.lot_id,
                source_lots,
            )
            continue
        if any(lot_id in seen_source_lots for lot_id in source_lots):
            duplicate_source_excluded += 1
            logger.info(
                "[AUDIT_PICKTABLE_FILTER] zone=Z2 exclude lot=%s sources=%s reason=duplicate_source",
                jig_unload_obj.lot_id,
                source_lots,
            )
            continue
        active_rows.append(jig_unload_obj)
        seen_source_lots.update(source_lots)

    logger.info(
        "[AUDIT_PICKTABLE_FILTER] zone=Z2 input=%d output=%d direct_submission_excluded=%d partial_parent_excluded=%d completed_source_excluded=%d duplicate_source_excluded=%d completed_sources=%d",
        input_count,
        len(active_rows),
        direct_submission_excluded,
        partial_parent_excluded,
        completed_source_excluded,
        duplicate_source_excluded,
        len(completed_source_lots),
    )
    return active_rows
  


@method_decorator(login_required, name='dispatch')
class NA_Zone_PickTableView(APIView):
    """Nickel Audit Zone 2 Pick Table — mirrors NA_PickTableView (Zone 1) with zone_2 filter."""
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'Nickel_Audit - Zone_two/NickelAudit_PickTable_zone_two.html'

    def get(self, request):
        user = request.user
        is_admin = user.groups.filter(name='Admin').exists() if user.is_authenticated else False

        nq_rejection_reasons = Nickel_Audit_Rejection_Table.objects.all()

        allowed_color_ids = Plating_Color.objects.filter(
            jig_unload_zone_2=True
        ).values_list('id', flat=True)

        queryset = JigUnloadAfterTable.objects.select_related(
            'version', 'plating_color', 'polish_finish', 'na_hold_by', 'na_release_by'
        ).prefetch_related('location').filter(
            total_case_qty__gt=0,
            plating_color_id__in=allowed_color_ids
        )

        has_draft_subquery = Exists(
            Nickel_Audit_Draft_Store.objects.filter(lot_id=OuterRef('lot_id'))
        )
        draft_type_subquery = Nickel_Audit_Draft_Store.objects.filter(
            lot_id=OuterRef('lot_id')
        ).values('draft_type')[:1]

        # Scoped to rejection-reason records created after this lot's most
        # recent Nickel Wiping (re-)acceptance — a lot rejected in a prior
        # audit cycle and routed back to Nickel Wiping under the same
        # lot_id must show Reject Qty = 0 on its new cycle, not the stale
        # rejection quantity from before it was re-accepted.
        brass_rejection_qty_subquery = Nickel_Audit_Rejection_ReasonStore.objects.filter(
            lot_id=OuterRef('lot_id'),
            created_at__gt=OuterRef('nq_last_process_date_time'),
        ).values('total_rejection_quantity')[:1]

        # Scoped to submissions created after this lot's most recent Nickel
        # Wiping (re-)acceptance — see Nickel_Audit.views.NA_PickTableView
        # for the full rationale. An unscoped "has ANY NickelAudit_Submission
        # ever" check permanently blocked a lot from Nickel Audit's pick
        # table after its first audit pass, even after it cycled back
        # through Nickel Wiping and was re-accepted for a new audit cycle.
        has_submission_subquery = Exists(
            NickelAudit_Submission.objects.filter(
                lot_id=OuterRef('lot_id'),
                created_at__gt=OuterRef('nq_last_process_date_time'),
            )
        )

        is_nq_partial_accept_child_subquery = Exists(
            NickelQC_PartialAcceptLot.objects.filter(new_lot_id=OuterRef('lot_id'))
        )

        nq_partial_parent_lot_subquery = NickelQC_PartialAcceptLot.objects.filter(
            new_lot_id=OuterRef('lot_id')
        ).values('parent_lot_id')[:1]

        queryset = queryset.annotate(
            has_draft=has_draft_subquery,
            draft_type=draft_type_subquery,
            brass_rejection_total_qty=brass_rejection_qty_subquery,
            has_submission=has_submission_subquery,
            is_nq_partial_accept_child=is_nq_partial_accept_child_subquery,
            nq_partial_parent_lot_id=Subquery(nq_partial_parent_lot_subquery),
        )

        queryset = queryset.filter(
            (
                (
                    Q(na_qc_accptance__isnull=True) | Q(na_qc_accptance=False)
                ) &
                (
                    Q(na_qc_rejection__isnull=True) | Q(na_qc_rejection=False)
                    # A stale na_qc_rejection=True from a prior audit cycle must not
                    # block the lot forever — see Nickel_Audit.views.NA_PickTableView
                    # and _na_fresh_nw_reacceptance_q for the full rationale.
                    | (Q(na_qc_rejection=True) & _na_fresh_nw_reacceptance_q())
                ) &
                ~Q(na_qc_few_cases_accptance=True, na_onhold_picking=False)
                &
                (
                    Q(nq_qc_accptance=True) |
                    Q(is_nq_partial_accept_child=True) |
                    Q(nq_qc_few_cases_accptance=True, nq_onhold_picking=False)
                )
            )
            |
            Q(na_qc_rejection=True, na_onhold_picking=True)
        ).distinct().order_by('-nq_last_process_date_time', '-lot_id')

        page_number = request.GET.get('page', 1)
        completed_source_lots = _na_completed_source_lot_ids(allowed_color_ids)
        pick_rows = _active_audit_zone_pick_rows(queryset, completed_source_lots)
        paginator = Paginator(pick_rows, 10)
        page_obj = paginator.get_page(page_number)

        master_data = []
        for jig_unload_obj in page_obj.object_list:
            data = {
                'batch_id': jig_unload_obj.unload_lot_id,
                'lot_id': jig_unload_obj.lot_id,
                'date_time': jig_unload_obj.created_at,
                'model_stock_no__model_no': 'Combined Model',
                'plating_color': jig_unload_obj.plating_color.plating_color if jig_unload_obj.plating_color else '',
                'polish_finish': jig_unload_obj.polish_finish.polish_finish if jig_unload_obj.polish_finish else '',
                'version__version_name': jig_unload_obj.version.version_name if jig_unload_obj.version else '',
                'vendor_internal': '',
                'location__location_name': _get_input_source(jig_unload_obj),
                'tray_type': get_model_master_tray_info(jig_unload_obj.plating_stk_no, jig_unload_obj.tray_type or '')[0],
                'tray_capacity': _na_tray_capacity(
                    get_model_master_tray_info(jig_unload_obj.plating_stk_no, jig_unload_obj.tray_type or '')[0]
                ) or _na_tray_capacity(jig_unload_obj.tray_type or '') or jig_unload_obj.tray_capacity or 0,
                'stock_lot_id': jig_unload_obj.lot_id,
                'total_IP_accpeted_quantity': jig_unload_obj.total_case_qty,
                'na_ac_accepted_qty_verified': jig_unload_obj.na_ac_accepted_qty_verified,
                'nq_qc_accepted_qty': jig_unload_obj.nq_qc_accepted_qty,
                'na_missing_qty': jig_unload_obj.na_missing_qty,
                'na_physical_qty': jig_unload_obj.na_physical_qty,
                'accepted_tray_scan_status': jig_unload_obj.na_accepted_tray_scan_status,
                'na_pick_remarks': jig_unload_obj.na_pick_remarks,
                'nq_pick_remarks': jig_unload_obj.nq_pick_remarks,
                'nq_qc_accptance': jig_unload_obj.nq_qc_accptance,
                'na_accepted_tray_scan_status': jig_unload_obj.na_accepted_tray_scan_status,
                'na_qc_rejection': _na_effective_qc_rejection(jig_unload_obj),
                'na_qc_few_cases_accptance': jig_unload_obj.na_qc_few_cases_accptance,
                'na_onhold_picking': jig_unload_obj.na_onhold_picking,
                'na_draft': jig_unload_obj.na_draft,
                'send_to_nickel_brass': jig_unload_obj.send_to_nickel_brass,
                'nq_last_process_date_time': jig_unload_obj.nq_last_process_date_time,
                'iqf_last_process_date_time': None,
                'na_hold_lot': jig_unload_obj.na_hold_lot,
                'na_holding_reason': jig_unload_obj.na_holding_reason,
                'na_release_lot': jig_unload_obj.na_release_lot,
                'na_release_reason': jig_unload_obj.na_release_reason,
                'na_hold_by': jig_unload_obj.na_hold_by.username if jig_unload_obj.na_hold_by else '',
                'na_hold_at': timezone.localtime(jig_unload_obj.na_hold_at).strftime("%d-%b-%Y %I:%M %p") if jig_unload_obj.na_hold_at else '',
                'na_release_by': jig_unload_obj.na_release_by.username if jig_unload_obj.na_release_by else '',
                'na_release_at': timezone.localtime(jig_unload_obj.na_release_at).strftime("%d-%b-%Y %I:%M %p") if jig_unload_obj.na_release_at else '',
                'has_draft': jig_unload_obj.has_draft,
                'draft_type': jig_unload_obj.draft_type,
                'brass_rejection_total_qty': jig_unload_obj.brass_rejection_total_qty,
                'is_nq_partial_accept_child': bool(getattr(jig_unload_obj, 'is_nq_partial_accept_child', False)),
                'nq_partial_parent_lot_id': getattr(jig_unload_obj, 'nq_partial_parent_lot_id', '') or '',
                'nq_partial_accept_qty': getattr(jig_unload_obj, 'nq_partial_accept_qty', None) or jig_unload_obj.total_case_qty,
                'plating_stk_no': jig_unload_obj.plating_stk_no or '',
                'polishing_stk_no': jig_unload_obj.polish_stk_no or '',
                'category': jig_unload_obj.category or '',
                # Prefer the live current_stage SSOT (modelmasterapp/stage_service.py) so
                # this stays in sync with downstream modules (e.g. Spider Spindle) that
                # only update current_stage and not last_process_module.
                'last_process_module': jig_unload_obj.current_stage or jig_unload_obj.last_process_module or 'Jig Unload',
                'combine_lot_ids': jig_unload_obj.combine_lot_ids,
                'unload_lot_id': jig_unload_obj.unload_lot_id,
                'na_qc_acceptance': jig_unload_obj.na_qc_accptance,
                'audit_check': jig_unload_obj.audit_check,
            }

            images = []
            if jig_unload_obj.plating_stk_no:
                plating_stk_no = str(jig_unload_obj.plating_stk_no)
                if len(plating_stk_no) >= 4:
                    model_no_prefix = plating_stk_no[:4]
                    try:
                        model_master = ModelMaster.objects.filter(
                            model_no__startswith=model_no_prefix
                        ).prefetch_related('images').first()
                        if model_master:
                            for img in _sort_images_front_first_safe(model_master.images.all()):
                                if img.master_image:
                                    images.append(img.master_image.url)
                    except Exception:
                        pass
            if not images and data['combine_lot_ids']:
                first_lot_id = data['combine_lot_ids'][0] if data['combine_lot_ids'] else None
                if first_lot_id:
                    total_stock = TotalStockModel.objects.filter(lot_id=first_lot_id).first()
                    if total_stock and total_stock.batch_id and total_stock.batch_id.model_stock_no:
                        for img in _sort_images_front_first_safe(total_stock.batch_id.model_stock_no.images.all()):
                            if img.master_image:
                                images.append(img.master_image.url)
            if not images:
                images = [static('assets/images/imagePlaceholder.jpg')]
            data['model_images'] = images
            master_data.append(data)

        type_of_input_map = get_type_of_input_map([data.get('stock_lot_id') for data in master_data])
        for data in master_data:
            tray_capacity = data.get('tray_capacity', 0)
            data['vendor_location'] = f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"
            lot_id = data.get('stock_lot_id')
            data['type_of_input'] = type_of_input_map.get(lot_id, 'Fresh')

            jig_unload_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()

            total_rejection_qty = 0
            rejection_store = Nickel_Audit_Rejection_ReasonStore.objects.filter(lot_id=lot_id).first()
            # A rejection store row from a prior audit cycle (lot rejected,
            # then routed back to Nickel Wiping and re-accepted under the
            # same lot_id) must not be subtracted from this new cycle's
            # accepted qty — only apply it if it postdates the lot's most
            # recent Nickel Wiping (re-)acceptance.
            if (
                rejection_store and rejection_store.total_rejection_quantity
                and jig_unload_obj and jig_unload_obj.nq_last_process_date_time
                and rejection_store.created_at > jig_unload_obj.nq_last_process_date_time
            ):
                total_rejection_qty = rejection_store.total_rejection_quantity

            if jig_unload_obj and total_rejection_qty > 0:
                data['display_accepted_qty'] = max(jig_unload_obj.nq_qc_accepted_qty - total_rejection_qty, 0)
            else:
                data['display_accepted_qty'] = jig_unload_obj.nq_qc_accepted_qty if jig_unload_obj else 0

            na_physical_qty = data.get('na_physical_qty') or 0
            brass_rejection_total_qty = data.get('brass_rejection_total_qty') or 0
            data['is_delink_only'] = (na_physical_qty > 0 and
                                      brass_rejection_total_qty >= na_physical_qty and
                                      data.get('na_onhold_picking', False))

            display_qty = data.get('display_accepted_qty', 0)
            data['no_of_trays'] = math.ceil(display_qty / tray_capacity) if tray_capacity > 0 and display_qty > 0 else 0

            data['available_qty'] = na_physical_qty if na_physical_qty > 0 else data.get('total_IP_accpeted_quantity', 0)

            display_accepted_qty = data.get('display_accepted_qty', 0)
            aql_plan = AQLSamplingPlan.objects.filter(
                lot_qty_from__lte=display_accepted_qty,
                lot_qty_to__gte=display_accepted_qty
            ).first()
            if aql_plan:
                data['aql_limit'] = float(aql_plan.aql_limit)
                data['sample_qty'] = aql_plan.sample_qty
            else:
                data['aql_limit'] = None
                data['sample_qty'] = None

        context = {
            'master_data': master_data,
            'page_obj': page_obj,
            'paginator': paginator,
            'user': user,
            'is_admin': is_admin,
            'nq_rejection_reasons': nq_rejection_reasons,
            'pick_table_count': len(master_data),
        }
        logger.info(
            "[AUDIT_PICKTABLE_FILTER] zone=Z2 page_rows=%d lot_ids=%s",
            len(master_data),
            [data['stock_lot_id'] for data in master_data],
        )
        return Response(context, template_name=self.template_name)


@method_decorator(login_required, name='dispatch')
class NA_Zone_CompletedView(APIView):
    """Nickel Audit Zone 2 Completed Table — mirrors NACompletedView (Zone 1) with zone_2 filter."""
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'Nickel_Audit - Zone_two/NickelAudit_Completed_zone_two.html'

    def get(self, request):
        from django.utils import timezone
        from datetime import datetime, timedelta
        import pytz

        user = request.user
        tz = pytz.timezone("Asia/Kolkata")
        now_local = timezone.now().astimezone(tz)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        from_date_str = request.GET.get("from_date")
        to_date_str = request.GET.get("to_date")
        if from_date_str and to_date_str:
            try:
                from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
                to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
            except ValueError:
                from_date = yesterday
                to_date = today
        else:
            from_date = yesterday
            to_date = today

        from_datetime = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
        to_datetime = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))

        allowed_color_ids = Plating_Color.objects.filter(
            jig_unload_zone_2=True
        ).values_list("id", flat=True)

        # ERR4 Fix: list one row per completed submission event (append-only
        # NickelAudit_Submission history), not one row per live
        # JigUnloadAfterTable object — a Full Reject routes the same row
        # back to Nickel Wiping for rework instead of creating a new one, so
        # the latter silently collapsed multiple completed audit passes for
        # the same physical lot into a single row.
        completed_rows = _na_completed_event_rows(allowed_color_ids)
        completed_rows = [
            r for r in completed_rows
            if r.na_last_process_date_time
            and from_datetime <= r.na_last_process_date_time <= to_datetime
        ]

        page_number = request.GET.get("page", 1)
        paginator = Paginator(completed_rows, 10)
        page_obj = paginator.get_page(page_number)

        master_data = []
        for jig_unload_obj in page_obj.object_list:
            # accepted_qty/rejected_qty/no_of_trays come straight from this
            # row's own NickelAudit_Submission event (set by
            # _na_completed_event_rows) — no need to re-derive them via
            # _na_completed_lot_totals's "latest submission for this lot_id"
            # lookup, which would pick up a later, unrelated event.
            accepted_qty = jig_unload_obj.na_qc_accepted_qty or 0
            rejected_qty = getattr(jig_unload_obj, '_na_rejected_qty', 0)
            no_of_trays = getattr(jig_unload_obj, '_na_no_of_trays', 0)
            data = {
                "batch_id": jig_unload_obj.unload_lot_id,
                "lot_id": jig_unload_obj.lot_id,
                "date_time": jig_unload_obj.created_at,
                "model_stock_no__model_no": "Combined Model",
                "plating_color": jig_unload_obj.plating_color.plating_color if jig_unload_obj.plating_color else "",
                "polish_finish": jig_unload_obj.polish_finish.polish_finish if jig_unload_obj.polish_finish else "",
                "version__version_name": jig_unload_obj.version.version_name if jig_unload_obj.version else "",
                "vendor_internal": "",
                "location__location_name": _get_input_source(jig_unload_obj),
                "tray_type": get_model_master_tray_info(jig_unload_obj.plating_stk_no, jig_unload_obj.tray_type or "")[0],
                "tray_capacity": jig_unload_obj.tray_capacity or 0,
                "stock_lot_id": jig_unload_obj.lot_id,
                # Prefer the live current_stage SSOT (modelmasterapp/stage_service.py) so
                # this stays in sync with downstream modules (e.g. Spider Spindle) that
                # only update current_stage and not last_process_module.
                "last_process_module": jig_unload_obj.current_stage or jig_unload_obj.last_process_module or "Jig Unload",
                "total_IP_accpeted_quantity": jig_unload_obj.total_case_qty,
                "na_qc_accptance": jig_unload_obj.na_qc_accptance,
                "na_qc_rejection": jig_unload_obj.na_qc_rejection,
                "na_qc_few_cases_accptance": jig_unload_obj.na_qc_few_cases_accptance,
                "na_onhold_picking": jig_unload_obj.na_onhold_picking,
                "na_hold_lot": jig_unload_obj.na_hold_lot,
                "na_holding_reason": jig_unload_obj.na_holding_reason,
                "na_release_lot": jig_unload_obj.na_release_lot,
                "na_release_reason": jig_unload_obj.na_release_reason,
                "na_physical_qty": jig_unload_obj.na_physical_qty,
                "na_missing_qty": jig_unload_obj.na_missing_qty or 0,
                "na_pick_remarks": jig_unload_obj.na_pick_remarks,
                "na_accepted_tray_scan_status": jig_unload_obj.na_accepted_tray_scan_status,
                "na_ac_accepted_qty_verified": jig_unload_obj.na_ac_accepted_qty_verified,
                "na_qc_accepted_qty": accepted_qty,
                "na_rejection_qty": rejected_qty,
                "na_last_process_date_time": jig_unload_obj.na_last_process_date_time,
                "plating_stk_no": jig_unload_obj.plating_stk_no or "",
                "polishing_stk_no": jig_unload_obj.polish_stk_no or "",
                "category": jig_unload_obj.category or "",
                "combine_lot_ids": jig_unload_obj.combine_lot_ids,
                "unload_lot_id": jig_unload_obj.unload_lot_id,
                "audit_check": jig_unload_obj.audit_check,
                # "Lot Qty" is the total quantity processed in this completion
                # event (accepted + rejected), not just the accepted portion —
                # for a Full Reject event accepted_qty is legitimately 0, so
                # falling back to accepted_qty alone showed "0" instead of the
                # lot's real total. total_case_qty (= this event's
                # NickelAudit_Submission.total_lot_qty) already carries that
                # correctly-scoped total.
                "display_accepted_qty": jig_unload_obj.total_case_qty or accepted_qty,
                "available_qty": accepted_qty or jig_unload_obj.na_physical_qty or jig_unload_obj.total_case_qty or 0,
                "no_of_trays": no_of_trays,
                # Lot is only "Released" once it has actually moved past this stage
                # (current_stage SSOT differs from 'Nickel Audit'). na_ac_accepted_qty_verified
                # only reflects the qty-check step done during picking, not a downstream move,
                # so it must not drive this pill (mirrors Inprocess_Inspection.lot_status).
                "lot_status": (
                    "Released"
                    if jig_unload_obj.current_stage and jig_unload_obj.current_stage != "Nickel Audit"
                    else "Yet to Release"
                ),
            }

            images = []
            if jig_unload_obj.plating_stk_no:
                plating_stk_no = str(jig_unload_obj.plating_stk_no)
                if len(plating_stk_no) >= 4:
                    model_no_prefix = plating_stk_no[:4]
                    model_master = (
                        ModelMaster.objects.filter(model_no__startswith=model_no_prefix)
                        .prefetch_related("images")
                        .first()
                    )
                    if model_master:
                        for img in _sort_images_front_first_safe(model_master.images.all()):
                            if img.master_image:
                                images.append(img.master_image.url)
            if not images and data["combine_lot_ids"]:
                first_lot_id = data["combine_lot_ids"][0] if data["combine_lot_ids"] else None
                if first_lot_id:
                    total_stock = TotalStockModel.objects.filter(lot_id=first_lot_id).first()
                    if total_stock and total_stock.batch_id and total_stock.batch_id.model_stock_no:
                        for img in _sort_images_front_first_safe(total_stock.batch_id.model_stock_no.images.all()):
                            if img.master_image:
                                images.append(img.master_image.url)
            if not images:
                images = [static("assets/images/imagePlaceholder.jpg")]
            data["model_images"] = images
            master_data.append(data)

        type_of_input_map = get_type_of_input_map([data.get("stock_lot_id") for data in master_data])
        for data in master_data:
            data["type_of_input"] = type_of_input_map.get(data.get("stock_lot_id"), "Fresh")

        context = {
            "master_data": master_data,
            "page_obj": page_obj,
            "paginator": paginator,
            "user": user,
            "from_date": from_date.strftime("%Y-%m-%d"),
            "to_date": to_date.strftime("%Y-%m-%d"),
            "date_filter_applied": bool(from_date_str and to_date_str),
        }
        return Response(context, template_name=self.template_name)