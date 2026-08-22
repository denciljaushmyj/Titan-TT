from django.urls import path

from Recovery_Brass_QC import views
from .views import *
 
urlpatterns = [
    path('recovery_iqf_picktable/', RecoveryIQFPickTableView.as_view(), name='recovery_iqf_picktable'),
    path('recovery_iqf_accept_table/', RecoveryIQFAcceptTableView.as_view(), name='recovery_iqf_accept_table'),

    path('recovery_iqf_save_hold_unhold_reason/', RecoveryIQFSaveHoldUnholdReasonAPIView.as_view(), name='recovery_iqf_save_hold_unhold_reason'),

    path('recovery_iqf_get_brass_rejection_quantities/', recovery_iqf_get_brass_rejection_quantities, name='recovery_iqf_get_brass_rejection_quantities'),

    path('recovery_iqf_complete_tray_validate/', RecoveryIQFTrayValidate_Complete_APIView.as_view(), name='recovery_iqf_complete_tray_validate'),
    path('recovery_iqf_CompleteTable_tray_id_list/', RecoveryIQFCompleteTableTrayIdListAPIView.as_view(), name='recovery_iqf_CompleteTable_tray_id_list'),
    path('recovery_iqf_RejectTable_tray_id_list/', RecoveryIQFRejectTableTrayIdListAPIView.as_view(), name='recovery_iqf_RejectTable_tray_id_list'),

    path('recovery_iqf_save_ip_checkbox/', RecoveryIQFSaveIPCheckboxView.as_view(), name='recovery_iqf_save_ip_checkbox'),
    path('recovery_iqf_save_ip_pick_remark/', RecoveryIQFSaveIPPickRemarkAPIView.as_view(), name='recovery_iqf_save_ip_pick_remark'),
    path('recovery_iqf_delete_batch/', RecoveryIQFDeleteBatchAPIView.as_view(), name='recovery_iqf_delete_batch'),
    path('recovery_iqf_accepted_form/', RecoveryIQF_Accepted_form.as_view(), name='recovery_iqf_accepted_form'),
    path('recovery_iqf_lot_rejection/', RecoveryIQFLotRejectionAPIView.as_view(), name='recovery_iqf_lot_rejection'),
    
    # Draft endpoints
    path('recovery_iqf_lot_rejection_draft/', RecoveryIQFLotRejectionDraftAPIView.as_view(), name='recovery_iqf_lot_rejection_draft'),
    path('recovery_iqf_tray_rejection_draft/', RecoveryIQFTrayRejectionDraftAPIView.as_view(), name='recovery_iqf_tray_rejection_draft'),
    path('recovery_iqf_clear_draft/', RecoveryIQFClearDraftAPIView.as_view(), name='recovery_iqf_clear_draft'),
    path('recovery_iqf_get_draft_data/', recovery_iqf_get_draft_data, name='recovery_iqf_get_draft_data'),
    path('recovery_iqf_get_all_drafts/', recovery_iqf_get_all_drafts, name='recovery_iqf_get_all_drafts'),
    
    path('recovery_iqf_tray_rejection/', RecoveryIQFTrayRejectionAPIView.as_view(), name='recovery_iqf_tray_rejection'),
    path('recovery_iqf_reject_check_tray_id/', recovery_iqf_reject_check_tray_id, name='recovery_iqf_reject_check_tray_id'),
    path('recovery_iqf_get_accepted_tray_scan_data/', recovery_iqf_get_accepted_tray_scan_data, name='recovery_iqf_get_accepted_tray_scan_data'),
    path('recovery_iqf_view_tray_list/', recovery_iqf_view_tray_list, name='recovery_iqf_view_tray_list'),
    path('recovery_iqf_check_tray_id/', recovery_iqf_check_tray_id, name='recovery_iqf_check_tray_id'),
    path('recovery_iqf_get_rejected_tray_scan_data/', recovery_iqf_get_rejected_tray_scan_data, name='recovery_iqf_get_rejected_tray_scan_data'),
    path('recovery_iqf_tray_validate/', RecoveryIQFTrayValidateAPIView.as_view(), name='recovery_iqf_tray_validate'),
    path('recovery_iqf_completed_table/', RecoveryIQFCompletedTableView.as_view(), name='recovery_iqf_completed_table'),
    path('recovery_iqf_rejection_table/', RecoveryIQFRejectTableView.as_view(), name='recovery_iqf_rejection_table'),
    path('recovery_iqf_get_rejection_details/', recovery_iqf_get_rejection_details, name='recovery_iqf_get_rejection_details'),
    path('recovery_get_tray_capacity/', recovery_get_tray_capacity, name='recovery_get_tray_capacity'),

    path('recovery_iqf_reject_check_tray_id_simple/', recovery_iqf_reject_check_tray_id_simple, name='recovery_iqf_reject_check_tray_id_simple'),
    path('recovery_iqf_get_delink_candidates/', recovery_iqf_get_delink_candidates, name='recovery_iqf_get_delink_candidates'),
    path('recovery_iqf_get_rejected_trays/', recovery_iqf_get_rejected_trays, name='recovery_iqf_get_rejected_trays'),
    path('recovery_iqf_get_remaining_trays/', recovery_iqf_get_remaining_trays, name='recovery_iqf_get_remaining_trays'),
    path('recovery_iqf_validate_delink_tray/', recovery_iqf_validate_delink_tray, name='recovery_iqf_validate_delink_tray'),
    path('recovery_iqf_process_all_tray_data/', recovery_iqf_process_all_tray_data, name='recovery_iqf_process_all_tray_data'),

    path('recovery_iqf_delink_selected_trays/', recovery_iqf_delink_selected_trays, name='recovery_iqf_delink_selected_trays'),

     # Optimal Distribution Draft URLs - Class-based view (recommended)
    path('recovery_optimal_distribution_draft/', RecoveryIQFOptimalDistributionDraftView.as_view(), name='recovery_iqf_optimal_distribution_draft'),
    
    # OR function-based views (alternative)
    path('recovery_iqf_check_optimal_distribution_draft/', recovery_iqf_check_optimal_distribution_draft, name='recovery_iqf_check_optimal_distribution_draft'),
    path('recovery_iqf_save_optimal_distribution_draft/', recovery_iqf_save_optimal_distribution_draft, name='recovery_iqf_save_optimal_distribution_draft'),
    path('recovery_iqf_load_optimal_distribution_draft/', recovery_iqf_load_optimal_distribution_draft, name='recovery_iqf_load_optimal_distribution_draft'),
    
    path('recovery_iqf_tray_delink_top_tray_calc/', IQFTrayDelinkTopTrayCalcAPIView.as_view(), name='recovery_iqf_tray_delink_top_tray_calc'),
    path('recovery_iqf_validate_tray_id/', IQFValidateTrayIdAPIView.as_view(), name='recovery_iqf_validate_tray_id'),
    path('recovery_iqf_tray_delink_and_top_tray_update/', IQFTrayDelinkAndTopTrayUpdateAPIView.as_view(), name='recovery_iqf_tray_delink_and_top_tray_update'),

]