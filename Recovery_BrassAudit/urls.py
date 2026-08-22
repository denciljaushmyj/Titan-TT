from django.urls import path

from Recovery_DP import views
from .views import *

urlpatterns = [
    path('recovery_brass_audit_picktable/', RecoveryBrassAuditPickTableView.as_view(), name='recovery_brass_audit_picktable'),
    path('recovery_brass_audit_completed/', RecoveryBrassAuditCompletedView.as_view(), name='recovery_brass_audit_completed'),
    path('recovery_brass_audit_rejection/', RecoveryBrassAuditRejectTableView.as_view(), name='recovery_brass_audit_rejection'),

    
    path('recovery_brass_audit_save_hold_unhold_reason/', RecoveryBrassAudit_SaveHoldUnholdReasonAPIView.as_view(), name='recovery_brass_audit_save_hold_unhold_reason'),
    path('recovery_brass_get_tray_capacity_for_lot/', recovery_brass_get_tray_capacity_for_lot, name='recovery_brass_get_tray_capacity_for_lot'),
    path('recovery_brass_audit_save_ip_checkbox/', RecoveryBrassAudit_SaveIPCheckboxView.as_view(), name='recovery_brass_audit_save_ip_checkbox'),
    path('recovery_brass_save_ip_pick_remark/', RecoveryBrassSaveIPPickRemarkAPIView.as_view(), name='recovery_brass_save_ip_pick_remark'),
    path('recovery_brass_delete_batch/', RecoveryBQDeleteBatchAPIView.as_view(), name='recovery_brass_delete_batch'),
    path('recovery_brass_audit_accepted_form/', RecoveryBrass_Audit_Accepted_form.as_view(), name='recovery_brass_audit_accepted_form'),
    
    path('recovery_brass_audit_batch_rejection/', RecoveryAuditBatchRejectionAPIView.as_view(), name='recovery_brass_audit_batch_rejection'),
    path('recovery_brass_audit_tray_rejection/', RecoveryBrassAudit_TrayRejectionAPIView.as_view(), name='recovery_brass_audit_tray_rejection'),
    path('recovery_brass_audit_reject_check_tray_id/', recovery_brass_audit_reject_check_tray_id, name='recovery_brass_audit_reject_check_tray_id'),
    path('recovery_brass_audit_get_accepted_tray_scan_data/', recovery_brass_audit_get_accepted_tray_scan_data, name='recovery_brass_audit_get_accepted_tray_scan_data'),
    path('recovery_brass_audit_view_tray_list/', recovery_brass_audit_view_tray_list, name='recovery_brass_audit_view_tray_list'),
    path('recovery_brass_audit_save_accepted_tray_scan/', recovery_brass_audit_save_accepted_tray_scan, name='recovery_brass_audit_save_accepted_tray_scan'),
    path('recovery_brass_audit_check_tray_id/', recovery_brass_audit_check_tray_id, name='recovery_brass_audit_check_tray_id'),
    path('recovery_brass_audit_get_rejected_tray_scan_data/', recovery_brass_audit_get_rejected_tray_scan_data, name='recovery_brass_audit_get_rejected_tray_scan_data'),
    path('recovery_brass_audit_tray_validate/', RecoveryBrassAudit_TrayValidateAPIView.as_view(), name='recovery_brass_audit_tray_validate'),
    path('recovery_brass_audit_save_single_top_tray_scan/', recovery_brass_audit_save_single_top_tray_scan, name='recovery_brass_audit_save_single_top_tray_scan'),
    path('recovery_brass_audit_reject_check_tray_id_simple/', recovery_brass_audit_reject_check_tray_id_simple, name='recovery_brass_audit_reject_check_tray_id_simple'),
    
    path('recovery_brass_audit_get_delink_tray_data/', recovery_brass_audit_get_delink_tray_data, name='recovery_brass_audit_get_delink_tray_data'),
    path('recovery_brass_audit_delink_check_tray_id/', recovery_brass_audit_delink_check_tray_id, name='recovery_brass_audit_delink_check_tray_id'),
    
    path('recovery_brass_CompleteTable_tray_id_list/', RecoveryBrassTrayIdList_Complete_APIView.as_view(), name='recovery_brass_CompleteTable_tray_id_list'),
    path('recovery_brass_complete_tray_validate/', RecoveryBrassTrayValidate_Complete_APIView.as_view(), name='recovery_brass_complete_tray_validate'),

    # Draft functionality endpoints
    path('recovery_brass_audit_batch_rejection_draft/', RecoveryBrassAuditBatchRejectionDraftAPIView.as_view(), name='recovery_brass_audit_batch_rejection_draft'),
    path('recovery_brass_audit_tray_rejection_draft/', RecoveryBrassTrayRejectionDraftAPIView.as_view(), name='recovery_brass_audit_tray_rejection_draft'),
    path('recovery_brass_get_draft_data/', recovery_brass_get_draft_data, name='recovery_brass_get_draft_data'),
    path('recovery_brass_clear_draft/', RecoveryBrassClearDraftAPIView.as_view(), name='recovery_brass_clear_draft'),
    path('recovery_brass_get_all_drafts/', recovery_brass_get_all_drafts, name='recovery_brass_get_all_drafts'),

    path('recovery_brass_audit_get_top_tray_scan_draft/', recovery_brass_audit_get_top_tray_scan_draft, name='recovery_brass_audit_get_top_tray_scan_draft'),
    
    #Pick table Vlaidation
    path('recovery_pick_complete_tray_validate/', RecoveryPickTrayValidate_Complete_APIView.as_view(), name='recovery_pick_complete_tray_validate'),
    path('recovery_pick_CompleteTable_tray_id_list/', RecoveryPickTrayIdList_Complete_APIView.as_view(), name='recovery_pick_CompleteTable_tray_id_list'),

    #After tray validation  check
    path('recovery_AfterCheck_complete_tray_validate/', RecoveryAfterCheckTrayValidate_Complete_APIView.as_view(), name='recovery_AfterCheck_complete_tray_validate'),
    path('recovery_AfterCheck_pick_CompleteTable_tray_id_list/', RecoveryAfterCheckPickTrayIdList_Complete_APIView.as_view(), name='recovery_AfterCheck_pick_CompleteTable_tray_id_list'),

    path('recovery_brass_get_rejection_details/', recovery_brass_get_rejection_details, name='recovery_brass_get_rejection_details'),
    
    path('recovery_brass_audit_tray_delink_top_tray_calc/', BATrayDelinkTopTrayCalcAPIView.as_view(), name='recovery_brass_audit_tray_delink_top_tray_calc'),
    path('recovery_brass_audit_validate_tray_id/',BAValidateTrayIdAPIView.as_view(), name='recovery_brass_audit_validate_tray_id'),
    path('recovery_brass_audit_tray_delink_and_top_tray_update/', BATrayDelinkAndTopTrayUpdateAPIView.as_view(), name='recovery_brass_audit_tray_delink_and_top_tray_update'),
    path('recovery_RejectTable_tray_id_list/', RejectTableTrayIdListAPIView.as_view(), name='recovery_RejectTable_tray_id_list'),
    path('recovery_Reject_tray_validate/', RejectCheckTrayValidate_Complete_APIView.as_view(), name='recovery_Reject_tray_validate'),

]