"""
Optimized dashboard stats query layer with TIMING INSTRUMENTATION.
Uses aggregate() with Case/When to batch queries instead of multiple count() calls.
Reduces ~35 separate queries to ~8 total queries.
"""
from django.db.models import Count, Q, Case, When, IntegerField, Value
from django.db import close_old_connections
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed
from modelmasterapp.models import ModelMasterCreation, TotalStockModel
from Brass_QC.models import BrassTrayId as BQ_TrayId, Brass_Qc_Accepted_TrayScan, Brass_Qc_Accepted_TrayID_Store
from Jig_Loading.models import JigCompleted, JigLoadingManualDraft
from Jig_Unloading.models import JigUnloadAfterTable, JigUnloadDraft
import logging
import time
from .service_performance_logging import (
    duration_ms as service_duration_ms,
    emit_service_end,
    emit_service_error,
    emit_service_start,
    emit_thread_end,
    emit_thread_error,
    emit_thread_start,
    perf_counter as service_perf_counter,
)

logger = logging.getLogger(__name__)
DASHBOARD_STATS_MAX_WORKERS = 6


def get_day_planning_stats():
    """
    Batch 5 separate queries into 1.
    Query: ModelMasterCreation + TotalStockModel aggregates in single DB call.
    """
    # Day Planning batch query
    mmc_stats = ModelMasterCreation.objects.aggregate(
        yet_to_start=Count('pk', filter=Q(Draft_Saved=False)),
        jumbo_count=Count('pk', filter=Q(Draft_Saved=False, tray_type__icontains='Jumbo')),
        normal_count=Count('pk', filter=Q(Draft_Saved=False, tray_type__icontains='Normal')),
    )
    
    # Processed query (separate, can't batch with different table filter)
    dp_processed = TotalStockModel.objects.filter(
        Q(ip_person_qty_verified=True) | Q(draft_tray_verify=True) |
        Q(accepted_Ip_stock=True) | Q(few_cases_accepted_Ip_stock=True) |
        Q(rejected_ip_stock=True)
    ).count()
    
    yet_to_start = mmc_stats['yet_to_start']
    jumbo_count = mmc_stats['jumbo_count']
    normal_count = mmc_stats['normal_count']
    
    dp_total = yet_to_start + dp_processed
    dp_progress = int((dp_processed / max(dp_total, 1)) * 100)
    
    return {
        'label': 'Day Planning',
        'total_lot': dp_total,
        'yet_to_start': yet_to_start,
        'yet_to_start_percent': int((yet_to_start / max(dp_total, 1)) * 100),
        'drafted': normal_count,
        'drafted_percent': int((normal_count / max(dp_total, 1)) * 100),
        'processed': dp_processed,
        'processed_percent': dp_progress,
        'in_progress': jumbo_count,
        'in_progress_percent': int((jumbo_count / max(dp_total, 1)) * 100),
        'progress': dp_progress,
        'completed_percent': dp_progress,
        'moved_to_next_percent': int((jumbo_count / max(dp_total, 1)) * 100),
        'color': '#008080',
        'icon': 'mdi-package-variant-closed',
        'display_stats': [
            {'label': 'Total Batches', 'value': yet_to_start, 'unit': f'{yet_to_start}/{dp_total}', 'icon': 'mdi-folder-multiple'},
            {'label': 'Processed', 'value': dp_processed, 'unit': 'Completed', 'icon': 'mdi-check-circle'},
            {'label': 'Jumbo Tray Count', 'value': jumbo_count, 'unit': 'Loaded batches', 'icon': 'mdi-arrow-right-circle'},
            {'label': 'Normal Tray Count', 'value': normal_count, 'unit': 'Loaded batches', 'icon': 'mdi-package-variant'},
        ],
        'labels': {
            'total_lots': 'Total Rows (Yet to Start)',
            'progress': 'Total Processed in Complete Table',
            'in_progress': 'Jumbo Tray Count',
            'status_overview': 'Status Overview',
        },
    }


def get_input_screening_stats():
    """Return Input Screening card counts using submitted-table SSOT rows."""
    from InputScreening.models import (
        IS_PartialAcceptLot,
        IS_PartialRejectLot,
        InputScreening_Submitted,
    )

    submitted_lots = InputScreening_Submitted.objects.filter(
        is_submitted=True,
        is_active=True,
    ).values('lot_id')

    pending_pick_rows = (
        TotalStockModel.objects.filter(batch_id__Moved_to_D_Picker=True)
        .exclude(lot_id__in=submitted_lots)
        .exclude(
            Q(accepted_Ip_stock=True)
            | Q(accepted_tray_scan_status=True)
            | Q(rejected_ip_stock=True)
            | Q(remove_lot=True)
        )
        .count()
    )

    accepted_count = IS_PartialAcceptLot.objects.count()
    rejected_count = IS_PartialRejectLot.objects.count()
    completed_count = InputScreening_Submitted.objects.filter(is_submitted=True, is_active=True).count()

    return {
        'label': 'Input Screening', 'color': '#00897b', 'icon': 'mdi-format-list-checks',
        'total_input_qty': pending_pick_rows,
        'accepted_qty': accepted_count,
        'rejected_qty': rejected_count,
        'completed_qty': completed_count,
        'display_stats': [
            {'label': 'Total Rows in Pick Table', 'value': pending_pick_rows, 'unit': 'Rows', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': accepted_count, 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': rejected_count, 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': completed_count, 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_brass_qc_stats():
    """
    Batch 4 separate queries into 2.
    Uses distinct().count() which requires separate queries but optimized.
    """
    # Batch query 1: Distinct lot counts
    bq_total = BQ_TrayId.objects.values('lot_id').distinct().count()
    bq_acc = Brass_Qc_Accepted_TrayScan.objects.values('lot_id').distinct().count()
    
    # Batch query 2: TotalStockModel aggregates
    tsm_stats = TotalStockModel.objects.aggregate(
        bq_rej=Count('pk', filter=Q(brass_qc_rejection=True)),
    )
    bq_rej = tsm_stats['bq_rej']
    
    # Query 3: Completed (separate)
    bq_comp = Brass_Qc_Accepted_TrayID_Store.objects.filter(is_save=True).values('lot_id').distinct().count()
    
    return {
        'label': 'Brass QC', 'color': '#00796b', 'icon': 'mdi-shield-check',
        'total_qty': bq_total, 'accepted_qty': bq_acc, 'rejected_qty': bq_rej, 'completed_qty': bq_comp,
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': bq_total, 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': bq_acc, 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': bq_rej, 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': bq_comp, 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_brass_audit_stats():
    """
    Batch 4 separate queries into 1.
    All filters on same table (TotalStockModel).
    """
    stats = TotalStockModel.objects.aggregate(
        ba_total=Count('pk', filter=Q(brass_qc_accptance=True)),
        ba_acc=Count('pk', filter=Q(Q(brass_audit_accptance=True) | Q(brass_audit_few_cases_accptance=True))),
        ba_rej=Count('pk', filter=Q(brass_audit_rejection=True)),
        ba_comp=Count('pk', filter=Q(Q(brass_audit_accptance=True) | Q(brass_audit_few_cases_accptance=True) | Q(brass_audit_rejection=True))),
    )
    
    return {
        'label': 'Brass Audit', 'color': '#00695c', 'icon': 'mdi-clipboard-check',
        'total_qty': stats['ba_total'], 'accepted_qty': stats['ba_acc'], 
        'rejected_qty': stats['ba_rej'], 'completed_qty': stats['ba_comp'],
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': stats['ba_total'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': stats['ba_acc'], 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': stats['ba_rej'], 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': stats['ba_comp'], 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_iqf_stats():
    """
    Batch 4 separate queries into 1.
    All filters on same table (TotalStockModel).
    """
    stats = TotalStockModel.objects.aggregate(
        iq_total=Count('pk', filter=Q(Q(brass_qc_rejection=True) | Q(send_brass_audit_to_iqf=True) | Q(brass_qc_few_cases_accptance=True))),
        iq_acc=Count('pk', filter=Q(Q(iqf_acceptance=True) | Q(iqf_few_cases_acceptance=True))),
        iq_rej=Count('pk', filter=Q(iqf_rejection=True)),
        iq_comp=Count('pk', filter=Q(Q(iqf_acceptance=True) | Q(iqf_few_cases_acceptance=True) | Q(iqf_rejection=True))),
    )
    
    return {
        'label': 'IQF', 'color': '#00897b', 'icon': 'mdi-filter-check',
        'total_qty': stats['iq_total'], 'accepted_qty': stats['iq_acc'], 
        'rejected_qty': stats['iq_rej'], 'completed_qty': stats['iq_comp'],
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': stats['iq_total'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': stats['iq_acc'], 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': stats['iq_rej'], 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': stats['iq_comp'], 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_jig_loading_stats():
    """
    Batch 3 separate queries into 1.
    """
    stats = JigCompleted.objects.aggregate(
        jl_loaded=Count('*'),
    )
    jl_draft = JigLoadingManualDraft.objects.count()
    jl_total = TotalStockModel.objects.filter(
        Q(brass_audit_accptance=True, Jig_Load_completed=False) |
        Q(brass_audit_few_cases_accptance=True, Jig_Load_completed=False)
    ).count()
    
    jl_loaded = stats['jl_loaded']
    jl_remain = max(jl_total - jl_loaded, 0)
    
    return {
        'label': 'Jig Loading', 'color': '#0097a7', 'icon': 'mdi-upload',
        'total_qty': jl_total, 'loaded_qty': jl_loaded, 'draft_qty': jl_draft, 'remaining_qty': jl_remain,
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': jl_total, 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Jig Loaded', 'value': jl_loaded, 'unit': 'Completed', 'icon': 'mdi-check-circle'},
            {'label': 'In Draft', 'value': jl_draft, 'unit': 'In Progress', 'icon': 'mdi-pencil-box'},
            {'label': 'Remaining', 'value': jl_remain, 'unit': 'Yet to Load', 'icon': 'mdi-clock-outline'},
        ],
    }


def get_jig_unloading_stats():
    """
    Batch 3 separate queries into 1.
    """
    stats = JigCompleted.objects.aggregate(
        ju_total=Count('*'),
    )
    ju_unloaded = JigUnloadAfterTable.objects.count()
    ju_draft = JigUnloadDraft.objects.count()
    
    ju_total = stats['ju_total']
    ju_remain = max(ju_total - ju_unloaded, 0)
    
    return {
        'label': 'Jig Unloading', 'color': '#00838f', 'icon': 'mdi-download',
        'total_qty': ju_total, 'unloaded_qty': ju_unloaded, 'draft_qty': ju_draft, 'remaining_qty': ju_remain,
        'display_stats': [
            {'label': 'Total Jigs Loaded', 'value': ju_total, 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Unloaded', 'value': ju_unloaded, 'unit': 'Processed', 'icon': 'mdi-check-circle'},
            {'label': 'In Draft', 'value': ju_draft, 'unit': 'In Progress', 'icon': 'mdi-pencil-box'},
            {'label': 'Remaining', 'value': ju_remain, 'unit': 'Yet to Unload', 'icon': 'mdi-clock-outline'},
        ],
    }


def get_inprocess_inspection_stats():
    """
    Batch 4 separate queries into 1.
    """
    stats = JigCompleted.objects.aggregate(
        ip_total=Count('*'),
        ip_inspected=Count('pk', filter=Q(jig_position__isnull=False)),
        ip_pending=Count('pk', filter=Q(jig_position__isnull=True)),
        ip_unloaded=Count('pk', filter=Q(last_process_module='Jig Unloading')),
    )
    
    return {
        'label': 'Inprocess Inspection', 'color': '#006064', 'icon': 'mdi-eye-check',
        'total_qty': stats['ip_total'], 'inspected_qty': stats['ip_inspected'], 
        'pending_qty': stats['ip_pending'], 'unloaded_qty': stats['ip_unloaded'],
        'display_stats': [
            {'label': 'Total Jigs', 'value': stats['ip_total'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Inspected', 'value': stats['ip_inspected'], 'unit': 'Assigned', 'icon': 'mdi-eye-check'},
            {'label': 'Pending', 'value': stats['ip_pending'], 'unit': 'In Pick Table', 'icon': 'mdi-clock-outline'},
            {'label': 'Unloaded', 'value': stats['ip_unloaded'], 'unit': 'Completed', 'icon': 'mdi-check-all'},
        ],
    }


def get_nickel_inspection_stats():
    """
    Batch 4 separate queries into 1.
    """
    stats = JigUnloadAfterTable.objects.aggregate(
        ni_total=Count('pk', filter=Q(total_case_qty__gt=0)),
        ni_acc=Count('pk', filter=Q(Q(nq_qc_accptance=True) | Q(nq_qc_few_cases_accptance=True))),
        ni_rej=Count('pk', filter=Q(nq_qc_rejection=True)),
        ni_comp=Count('pk', filter=Q(Q(nq_qc_accptance=True) | Q(nq_qc_few_cases_accptance=True) | Q(nq_qc_rejection=True))),
    )
    
    return {
        'label': 'Nickel Inspection', 'color': '#00838f', 'icon': 'mdi-microscope',
        'total_qty': stats['ni_total'], 'accepted_qty': stats['ni_acc'], 
        'rejected_qty': stats['ni_rej'], 'completed_qty': stats['ni_comp'],
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': stats['ni_total'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': stats['ni_acc'], 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': stats['ni_rej'], 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': stats['ni_comp'], 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_nickel_audit_stats():
    """
    Batch 4 separate queries into 1.
    """
    stats = JigUnloadAfterTable.objects.aggregate(
        na_total=Count('pk', filter=Q(Q(nq_qc_accptance=True) | Q(nq_qc_few_cases_accptance=True))),
        na_acc=Count('pk', filter=Q(Q(na_qc_accptance=True) | Q(na_qc_few_cases_accptance=True))),
        na_rej=Count('pk', filter=Q(na_qc_rejection=True)),
        na_comp=Count('pk', filter=Q(Q(na_qc_accptance=True) | Q(na_qc_few_cases_accptance=True) | Q(na_qc_rejection=True))),
    )
    
    return {
        'label': 'Nickel Audit', 'color': '#00695c', 'icon': 'mdi-clipboard-search',
        'total_qty': stats['na_total'], 'accepted_qty': stats['na_acc'], 
        'rejected_qty': stats['na_rej'], 'completed_qty': stats['na_comp'],
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': stats['na_total'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Accepted Count', 'value': stats['na_acc'], 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'Rejected Count', 'value': stats['na_rej'], 'unit': 'Count', 'icon': 'mdi-close-circle'},
            {'label': 'Completed Count', 'value': stats['na_comp'], 'unit': 'Count', 'icon': 'mdi-check-all'},
        ],
    }


def get_spider_spindle_stats():
    """Return combined Spider Spindle Z1/Z2 dashboard counts."""
    spider_scope = Q(total_case_qty__gt=0, na_qc_accptance=True) & (
        Q(plating_color__jig_unload_zone_1=True) |
        Q(plating_color__jig_unload_zone_2=True)
    )
    z1_pending = Q(plating_color__jig_unload_zone_1=True, ss_z1_completed=False)
    z2_pending = Q(plating_color__jig_unload_zone_2=True, ss_z2_completed=False)
    z1_completed = Q(plating_color__jig_unload_zone_1=True, ss_z1_completed=True)
    z2_completed = Q(plating_color__jig_unload_zone_2=True, ss_z2_completed=True)
    pending_scope = z1_pending | z2_pending

    stats = JigUnloadAfterTable.objects.aggregate(
        total_qty=Count('pk', filter=spider_scope & pending_scope),
        released_qty=Count('pk', filter=spider_scope & pending_scope & Q(spider_release_lot=True)),
        hold_qty=Count('pk', filter=spider_scope & pending_scope & Q(spider_hold_lot=True)),
        completed_qty=Count('pk', filter=spider_scope & (z1_completed | z2_completed)),
    )

    return {
        'label': 'Spider Spindle', 'color': '#00796b', 'icon': 'mdi-axis-arrow',
        'total_qty': stats['total_qty'],
        'released_qty': stats['released_qty'],
        'hold_qty': stats['hold_qty'],
        'completed_qty': stats['completed_qty'],
        'display_stats': [
            {'label': 'Total Lots in Pick Table', 'value': stats['total_qty'], 'unit': 'Lots', 'icon': 'mdi-table'},
            {'label': 'Released', 'value': stats['released_qty'], 'unit': 'Count', 'icon': 'mdi-check-circle'},
            {'label': 'On Hold', 'value': stats['hold_qty'], 'unit': 'Count', 'icon': 'mdi-pause-circle'},
            {'label': 'Completed', 'value': stats['completed_qty'], 'unit': 'Unloaded', 'icon': 'mdi-check-all'},
        ],
    }


DASHBOARD_STAT_PROVIDERS = [
    ('Day Planning', get_day_planning_stats),
    ('Input Screening', get_input_screening_stats),
    ('Brass QC', get_brass_qc_stats),
    ('Brass Audit', get_brass_audit_stats),
    ('IQF', get_iqf_stats),
    ('Jig Loading', get_jig_loading_stats),
    ('Jig Unloading', get_jig_unloading_stats),
    ('Inprocess Inspection', get_inprocess_inspection_stats),
    ('Nickel Inspection', get_nickel_inspection_stats),
    ('Nickel Audit', get_nickel_audit_stats),
    ('Spider Spindle', get_spider_spindle_stats),
]


def get_dashboard_stat_labels():
    return [label for label, _ in DASHBOARD_STAT_PROVIDERS]


def get_dashboard_stats_for_labels(labels=None):
    """
    Fetch dashboard stats for the requested labels only.
    This keeps login/dashboard rendering from calculating cards the user cannot see.
    """
    service_started = service_perf_counter()
    emit_service_start(
        'adminportal.get_dashboard_stats_for_labels',
        caller='dashboard_stats_provider_pool',
    )
    requested_labels = set(labels or get_dashboard_stat_labels())
    requested_providers = [
        (module_name, func)
        for module_name, func in DASHBOARD_STAT_PROVIDERS
        if module_name in requested_labels
    ]
    stats_by_index = [None] * len(requested_providers)

    total_start = time.time()

    def run_provider(index, module_name, func):
        provider_started = service_perf_counter()
        emit_thread_start(
            thread_name='dashboard-stats-provider',
            metadata={'provider_name': module_name},
        )
        emit_service_start(
            'adminportal.dashboard_stat_provider',
            caller='dashboard_stats_provider_pool',
            metadata={'provider_name': module_name},
        )
        close_old_connections()
        t1 = time.time()
        try:
            stat = func()
            provider_elapsed = service_duration_ms(provider_started)
            emit_service_end(
                'adminportal.dashboard_stat_provider',
                provider_elapsed,
                success=True,
                caller='dashboard_stats_provider_pool',
                metadata={'provider_name': module_name},
            )
            emit_thread_end(
                thread_name='dashboard-stats-provider',
                duration=provider_elapsed,
                result='completed',
                metadata={'provider_name': module_name},
            )
            return index, module_name, stat, (time.time() - t1) * 1000
        except Exception as exc:
            provider_elapsed = service_duration_ms(provider_started)
            emit_service_error(
                'adminportal.dashboard_stat_provider',
                exc,
                duration=provider_elapsed,
                caller='dashboard_stats_provider_pool',
                metadata={'provider_name': module_name},
            )
            emit_thread_error(
                'dashboard-stats-provider',
                exc,
                duration=provider_elapsed,
                metadata={'provider_name': module_name},
            )
            raise
        finally:
            close_old_connections()

    try:
        if requested_providers:
            max_workers = min(DASHBOARD_STATS_MAX_WORKERS, len(requested_providers))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(run_provider, index, module_name, func): index
                    for index, (module_name, func) in enumerate(requested_providers)
                }
                for future in as_completed(future_map):
                    index, module_name, stat, elapsed_ms = future.result()
                    if getattr(settings, 'ENABLE_DASHBOARD_LATENCY_LOGS', False):
                        logger.warning(f'MODULE_QUERY: {module_name} = {elapsed_ms:.2f}ms')
                    stats_by_index[index] = stat

        total_ms = (time.time() - total_start) * 1000
        if getattr(settings, 'ENABLE_DASHBOARD_LATENCY_LOGS', False):
            logger.warning(f'REQUESTED_MODULES_TOTAL: {total_ms:.2f}ms labels={list(requested_labels)}')

        stats = [stat for stat in stats_by_index if stat is not None]
        emit_service_end(
            'adminportal.get_dashboard_stats_for_labels',
            service_duration_ms(service_started),
            success=True,
            caller='dashboard_stats_provider_pool',
            metadata={
                'requested_count': len(requested_labels),
                'provider_count': len(requested_providers),
                'stats_count': len(stats),
            },
        )
        return stats
    except Exception as exc:
        emit_service_error(
            'adminportal.get_dashboard_stats_for_labels',
            exc,
            duration=service_duration_ms(service_started),
            caller='dashboard_stats_provider_pool',
            metadata={
                'requested_count': len(requested_labels),
                'provider_count': len(requested_providers),
            },
        )
        raise


def get_all_dashboard_stats():
    """
    Fetch all dashboard stats using optimized batch queries.
    Returns list of stat dicts for each module.
    Logs timing for each module query.
    """
    return get_dashboard_stats_for_labels()
