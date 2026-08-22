from django.shortcuts import render
from django.http import JsonResponse
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework import status
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, OuterRef, Subquery
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
import pytz
import json
import logging

from modelmasterapp.models import *
from datetime import datetime, timedelta  # re-import after wildcard (modelmasterapp shadows datetime)
from Jig_Unloading.models import JigUnloadAfterTable
from .models import SpiderSpindleZ1TrayId
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




def _get_upstream_tray_ids(lot_id, jig_obj=None):
    """Cascade tray lookup: NickelQcTrayId → Nickel_AuditTrayId → JigUnload_TrayId → IP_TrayVerificationStatus."""
    from Nickel_Inspection.models import NickelQcTrayId
    tray_ids = list(NickelQcTrayId.objects.filter(lot_id=lot_id, delink_tray=False).values_list('tray_id', flat=True))
    if tray_ids:
        return tray_ids

    from Nickel_Audit.models import Nickel_AuditTrayId
    tray_ids = list(Nickel_AuditTrayId.objects.filter(lot_id=lot_id, delink_tray=False).values_list('tray_id', flat=True))
    if tray_ids:
        return tray_ids

    from Jig_Unloading.models import JigUnload_TrayId
    tray_ids = list(JigUnload_TrayId.objects.filter(lot_id=lot_id, delink_tray=False).values_list('tray_id', flat=True))
    if tray_ids:
        return tray_ids

    # Fallback: check combine_lot_ids via IP_TrayVerificationStatus
    if jig_obj is None:
        jig_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
    if jig_obj and jig_obj.combine_lot_ids:
        from InputScreening.models import IP_TrayVerificationStatus
        for clid in jig_obj.combine_lot_ids:
            tray_ids = list(IP_TrayVerificationStatus.objects.filter(
                lot_id=clid, is_verified=True, verification_status='pass'
            ).values_list('tray_id', flat=True))
            if tray_ids:
                return tray_ids

    return []


def _release_spider_trays_for_reuse(lot_id, tray_ids):
    tray_ids = [tid for tid in dict.fromkeys(tray_ids or []) if tid]
    if not tray_ids:
        return 0

    from InputScreening.models import IPTrayId
    from Nickel_Inspection.models import NickelQcTrayId
    from Nickel_Audit.models import Nickel_AuditTrayId
    from Jig_Unloading.models import JigUnload_TrayId

    IPTrayId.objects.filter(lot_id=lot_id, tray_id__in=tray_ids).update(delink_tray=True)
    NickelQcTrayId.objects.filter(lot_id=lot_id, tray_id__in=tray_ids).update(delink_tray=True)
    Nickel_AuditTrayId.objects.filter(lot_id=lot_id, tray_id__in=tray_ids).update(delink_tray=True)
    JigUnload_TrayId.objects.filter(lot_id=lot_id, tray_id__in=tray_ids).update(delink_tray=True)
    TrayId.objects.filter(tray_id__in=tray_ids).update(
        lot_id=None,
        batch_id=None,
        tray_quantity=None,
        top_tray=False,
        ip_top_tray=False,
        ip_top_tray_qty=0,
        brass_top_tray=False,
        brass_top_tray_qty=0,
        iqf_top_tray=False,
        iqf_top_tray_qty=0,
        delink_tray=True,
        delink_tray_qty=None,
        new_tray=True,
        scanned=False,
    )
    return len(tray_ids)


def _get_input_source(jig_unload_obj):
    """Return location names with fallback chain."""
    names = [loc.location_name for loc in jig_unload_obj.location.all()]
    if not names:
        for raw_cid in (jig_unload_obj.combine_lot_ids or []):
            cid = raw_cid.rsplit('-', 1)[-1] if raw_cid and '-' in raw_cid else raw_cid
            if not cid:
                continue
            tsm = TotalStockModel.objects.filter(lot_id=cid).prefetch_related('location').select_related('batch_id__location').first()
            if tsm and tsm.location.exists():
                names = [loc.location_name for loc in tsm.location.all()]
                break
            if tsm and tsm.batch_id and tsm.batch_id.location:
                names = [tsm.batch_id.location.location_name]
                break
    return ', '.join(names)


def _get_model_images(jig_unload_obj):
    """Get model images from plating_stk_no → ModelMaster."""
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
    if not images and jig_unload_obj.combine_lot_ids:
        first_lot_id = jig_unload_obj.combine_lot_ids[0] if jig_unload_obj.combine_lot_ids else None
        if first_lot_id:
            total_stock = TotalStockModel.objects.filter(lot_id=first_lot_id).first()
            if total_stock and total_stock.batch_id and total_stock.batch_id.model_stock_no:
                for img in _sort_images_front_first_safe(total_stock.batch_id.model_stock_no.images.all()):
                    if img.master_image:
                        images.append(img.master_image.url)
    return images


def _split_tray_ids(tray_id_value):
    return [tray_id.strip() for tray_id in str(tray_id_value or '').split(',') if tray_id.strip()]


@method_decorator(login_required, name='dispatch')
class SSZ1PickTableView(APIView):
    """Spider Spindle Zone 1 Pick Table — IPS colors."""
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'SpiderSpindle_Z1/ss_z1_pick_table.html'

    def get(self, request):
        user = request.user
        is_admin = user.groups.filter(name='Admin').exists() if user.is_authenticated else False

        # Z1 = IPS colors (jig_unload_zone_1=True)
        allowed_color_ids = Plating_Color.objects.filter(
            jig_unload_zone_1=True
        ).values_list('id', flat=True)

        # Show lots that completed Nickel Audit (na_qc_accptance=True) and NOT yet spider-spindle-Z1 completed
        queryset = JigUnloadAfterTable.objects.select_related(
            'version', 'plating_color', 'polish_finish'
        ).prefetch_related('location').filter(
            total_case_qty__gt=0,
            plating_color_id__in=allowed_color_ids,
            na_qc_accptance=True,
            ss_z1_completed=False,
        ).order_by('-created_at', '-lot_id')

        # Pagination
        page_number = request.GET.get('page', 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)

        page_lot_ids = [obj.lot_id for obj in page_obj.object_list]
        type_of_input_map = get_type_of_input_map(page_lot_ids)

        master_data = []
        for obj in page_obj.object_list:
            # Get linked tray for this lot (if any)
            linked_tray = SpiderSpindleZ1TrayId.objects.filter(lot_id=obj.lot_id).first()
            images = _get_model_images(obj)

            data = {
                'lot_id': obj.lot_id,
                'unload_lot_id': obj.unload_lot_id,
                'date_time': obj.na_last_process_date_time or obj.created_at,
                'plating_color': obj.plating_color.plating_color if obj.plating_color else '',
                'polish_finish': obj.polish_finish.polish_finish if obj.polish_finish else '',
                'version': obj.version.version_name if obj.version else '',
                'location': _get_input_source(obj),
                'tray_type': obj.tray_type or '',
                'total_case_qty': obj.total_case_qty,
                'plating_stk_no': obj.plating_stk_no or '',
                'polishing_stk_no': obj.polish_stk_no or '',
                'category': obj.category or '',
                'last_process_module': obj.last_process_module or 'Nickel Audit',
                'previous_module': 'Nickel Audit',
                'previous_module_remark': obj.na_pick_remarks or '',
                'spider_pick_remarks': obj.spider_pick_remarks or '',
                'spider_hold_lot': obj.spider_hold_lot,
                'spider_holding_reason': obj.spider_holding_reason or '',
                'spider_release_lot': obj.spider_release_lot,
                'spider_release_reason': obj.spider_release_reason or '',
                'linked_tray_id': linked_tray.tray_id if linked_tray else '',
                'images': images,
                'type_of_input': type_of_input_map.get(obj.lot_id, 'Fresh'),
            }
            master_data.append(data)

        return Response({
            'master_data': master_data,
            'page_obj': page_obj,
            'is_admin': is_admin,
        })


@method_decorator(login_required, name='dispatch')
class SSZ1CompletedView(APIView):
    """Spider Spindle Zone 1 Completed Table."""
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'SpiderSpindle_Z1/ss_z1_completed.html'

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
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            except ValueError:
                from_date = yesterday
                to_date = today
        else:
            from_date = yesterday
            to_date = today

        from_datetime = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
        to_datetime = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))

        allowed_color_ids = Plating_Color.objects.filter(
            jig_unload_zone_1=True
        ).values_list('id', flat=True)

        queryset = JigUnloadAfterTable.objects.select_related(
            'version', 'plating_color', 'polish_finish'
        ).prefetch_related('location').filter(
            total_case_qty__gt=0,
            plating_color_id__in=allowed_color_ids,
            ss_z1_completed=True,
            ss_z1_completed_at__range=(from_datetime, to_datetime),
        ).order_by('-ss_z1_completed_at', '-lot_id')

        page_number = request.GET.get('page', 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)

        page_lot_ids = [obj.lot_id for obj in page_obj.object_list]
        linked_tray_map = {}
        for tray in SpiderSpindleZ1TrayId.objects.filter(lot_id__in=page_lot_ids).order_by('linked_at', 'id'):
            linked_tray_map.setdefault(tray.lot_id, []).append(tray.tray_id)

        type_of_input_map = get_type_of_input_map(page_lot_ids)

        master_data = []
        for obj in page_obj.object_list:
            linked_tray_ids = linked_tray_map.get(obj.lot_id) or _split_tray_ids(obj.ss_z1_tray_id)
            images = _get_model_images(obj)
            data = {
                'lot_id': obj.lot_id,
                'unload_lot_id': obj.unload_lot_id,
                'date_time': obj.created_at,
                'completed_at': obj.ss_z1_completed_at,
                'plating_color': obj.plating_color.plating_color if obj.plating_color else '',
                'polish_finish': obj.polish_finish.polish_finish if obj.polish_finish else '',
                'version': obj.version.version_name if obj.version else '',
                'location': _get_input_source(obj),
                'tray_type': obj.tray_type or '',
                'total_case_qty': obj.total_case_qty,
                'plating_stk_no': obj.plating_stk_no or '',
                'polishing_stk_no': obj.polish_stk_no or '',
                'category': obj.category or '',
                'linked_tray_id': ', '.join(linked_tray_ids),
                'linked_tray_ids': linked_tray_ids,
                'linked_tray_count': len(linked_tray_ids),
                'spider_pick_remarks': obj.spider_pick_remarks or '',
                'images': images,
                'type_of_input': type_of_input_map.get(obj.lot_id, 'Fresh'),
            }
            master_data.append(data)

        return Response({
            'master_data': master_data,
            'page_obj': page_obj,
            'from_date': from_date.strftime('%Y-%m-%d'),
            'to_date': to_date.strftime('%Y-%m-%d'),
        })


class SSZ1AddSpiderAPIView(APIView):
    """Add Spider: auto-fetch all trays from upstream, link them, mark completed."""

    def post(self, request):
        lot_id = request.data.get('lot_id')
        if not lot_id:
            return Response({'error': 'lot_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        jig_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id, ss_z1_completed=False).first()
        if not jig_obj:
            return Response({'error': 'Lot not found or already completed.'}, status=status.HTTP_404_NOT_FOUND)

        upstream_tray_ids = _get_upstream_tray_ids(lot_id, jig_obj)
        if not upstream_tray_ids:
            return Response({'error': 'No trays found for this lot.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                linked_tray_ids = []
                for tid in upstream_tray_ids:
                    if not SpiderSpindleZ1TrayId.objects.filter(lot_id=lot_id, tray_id=tid).exists():
                        SpiderSpindleZ1TrayId.objects.create(
                            lot_id=lot_id,
                            tray_id=tid,
                            linked_by=request.user if request.user.is_authenticated else None,
                        )
                    linked_tray_ids.append(tid)

                released_count = _release_spider_trays_for_reuse(lot_id, linked_tray_ids)

                jig_obj.ss_z1_completed = True
                jig_obj.ss_z1_tray_id = ','.join(linked_tray_ids)
                jig_obj.ss_z1_completed_at = timezone.now()
                jig_obj.ss_z1_completed_by = request.user if request.user.is_authenticated else None
                jig_obj.save(update_fields=[
                    'ss_z1_completed', 'ss_z1_tray_id', 'ss_z1_completed_at', 'ss_z1_completed_by'
                ])

                # Real processing activity — advance the shared current_stage SSOT
                # so the previous module (Jig Unloading) shows "Spider Spindle" as
                # the Current Location instead of a stale value.
                # jig_obj.lot_id is this JigUnloadAfterTable row's own ID, which never
                # exists in TotalStockModel — the original lot IDs tracked by Day
                # Planning/Brass QC/Brass Audit completed tables are in combine_lot_ids
                # (a jig can combine multiple original lots).
                from modelmasterapp.stage_service import update_juat_stage, update_stock_stage
                update_juat_stage(lot_id, 'Spider Spindle')
                for original_lot_id in (jig_obj.combine_lot_ids or []):
                    update_stock_stage(original_lot_id, 'Spider Spindle')
        except Exception:
            logger.exception("[SSZ1AddSpiderAPIView] failed lot_id=%s", lot_id)
            return Response({'success': False, 'error': 'Unable to add spider for this lot.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': True,
            'message': f'Spider added for lot {lot_id}. {released_count} trays released for reuse.',
            'trays': [{'tray_id': tid} for tid in linked_tray_ids],
        })


class SSZ1DelinkAPIView(APIView):
    """Delink: remove ALL tray links, mark TrayIds as reusable, revert completion."""

    def post(self, request):
        lot_id = request.data.get('lot_id')
        if not lot_id:
            return Response({'error': 'lot_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        jig_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
        if not jig_obj:
            return Response({'error': 'Lot not found.'}, status=status.HTTP_404_NOT_FOUND)

        linked_tray_ids = list(SpiderSpindleZ1TrayId.objects.filter(
            lot_id=lot_id
        ).values_list('tray_id', flat=True))
        if not linked_tray_ids and jig_obj.ss_z1_tray_id:
            linked_tray_ids = [tid.strip() for tid in jig_obj.ss_z1_tray_id.split(',') if tid.strip()]

        with transaction.atomic():
            SpiderSpindleZ1TrayId.objects.filter(lot_id=lot_id).delete()
            released_count = _release_spider_trays_for_reuse(lot_id, linked_tray_ids)

            jig_obj.ss_z1_completed = False
            jig_obj.ss_z1_tray_id = None
            jig_obj.ss_z1_completed_at = None
            jig_obj.ss_z1_completed_by = None
            jig_obj.save(update_fields=[
                'ss_z1_completed', 'ss_z1_tray_id', 'ss_z1_completed_at', 'ss_z1_completed_by'
            ])

        return Response({'success': True, 'message': f'{released_count} trays delinked for lot {lot_id}.'})


class SSZ1SaveRemarksAPIView(APIView):
    """Save spider pick remarks."""

    def post(self, request):
        lot_id = (request.data.get('lot_id') or '').strip()
        remarks = (request.data.get('remarks') or '').strip()
        if not lot_id:
            return Response({'success': False, 'error': 'lot_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not remarks:
            return Response({'success': False, 'error': 'remarks is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                jig_obj = JigUnloadAfterTable.objects.select_for_update().filter(lot_id=lot_id).first()
                if not jig_obj:
                    return Response({'success': False, 'error': 'Lot not found.'}, status=status.HTTP_404_NOT_FOUND)
                jig_obj.spider_pick_remarks = remarks
                jig_obj.save(update_fields=['spider_pick_remarks'])
            return Response({
                'success': True,
                'message': 'Remark saved successfully.',
                'lot_id': lot_id,
                'remark': remarks,
            })
        except Exception:
            logger.exception("[SSZ1SaveRemarksAPIView] failed lot_id=%s", lot_id)
            return Response({'success': False, 'error': 'Unable to save remark.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SSZ1GetTrayIdAPIView(APIView):
    """Auto-fetch the next available tray ID for a lot."""

    def get(self, request):
        lot_id = request.GET.get('lot_id')
        if not lot_id:
            return Response({'error': 'lot_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        jig_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
        if not jig_obj:
            return Response({'error': 'Lot not found.'}, status=status.HTTP_404_NOT_FOUND)

        upstream_tray_ids = _get_upstream_tray_ids(lot_id, jig_obj)
        tray_id = upstream_tray_ids[-1] if upstream_tray_ids else ''
        return Response({
            'tray_id': tray_id,
            'lot_id': lot_id,
            'total_case_qty': jig_obj.total_case_qty,
        })


class SSZ1GetAllTraysAPIView(APIView):
    """Fetch all tray IDs for a lot from upstream and linked records."""

    def get(self, request):
        lot_id = request.GET.get('lot_id')
        if not lot_id:
            return Response({'error': 'lot_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        jig_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
        if not jig_obj:
            return Response({'error': 'Lot not found.'}, status=status.HTTP_404_NOT_FOUND)

        linked_trays = list(SpiderSpindleZ1TrayId.objects.filter(
            lot_id=lot_id
        ).values_list('tray_id', flat=True))

        upstream_trays = _get_upstream_tray_ids(lot_id, jig_obj)

        all_tray_ids = list(dict.fromkeys(linked_trays + upstream_trays))

        trays = []
        for tid in all_tray_ids:
            trays.append({
                'tray_id': tid,
                'linked': tid in linked_trays,
            })

        return Response({
            'trays': trays,
            'lot_id': lot_id,
            'plating_stk_no': jig_obj.plating_stk_no or '',
            'total_case_qty': jig_obj.total_case_qty,
        })