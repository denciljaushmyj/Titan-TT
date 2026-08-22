from django.urls import path
from .views import *
 
urlpatterns = [
    path('rec_IS_PickTable/', RIS_PickTable.as_view(), name='rec_IS_PickTable'),
    path('rec_IS_RejectTable/', RIS_RejectTable.as_view(), name='rec_IS_RejectTable'),
    path('rec_save_ip_pick_remark/', RSaveIPPickRemarkAPIView.as_view(), name='rec_save_ip_pick_remark'),

    path('rec_save_ip_checkbox/', RSaveIPCheckboxView.as_view(), name='rec_save_ip_checkbox'),
    path('rec_ip_save_tray_draft/', RIPSaveTrayDraftAPIView.as_view(), name='rec_ip_save_tray_draft'),
    path('rec_get_tray_verification_status/', r_get_tray_verification_status, name='rec_get_tray_verification_status'),
    path('rec_reset_tray_verification_for_lot/', r_reset_tray_verification_for_lot, name='rec_reset_tray_verification_for_lot'),
 
    path('rec_is_accepted_form/', RIS_Accepted_form.as_view(), name='rec_is_accepted_form'),
    path('rec_batch_rejection/', RBatchRejectionAPIView.as_view(), name='rec_batch_rejection'),
    path('rec_tray_rejection/', RTrayRejectionAPIView.as_view(), name='rec_tray_rejection'),
    path('rec_get_accepted_tray_scan_data/', r_get_accepted_tray_scan_data, name='rec_get_accepted_tray_scan_data'),
    path('rec_ip_get_rejected_tray_scan_data/', r_ip_get_rejected_tray_scan_data, name='rec_ip_get_rejected_tray_scan_data'),
    path('rec_save_single_top_tray_scan/', r_save_single_top_tray_scan, name='rec_save_single_top_tray_scan'),

    path('rec_check_tray_id/', r_check_tray_id, name='rec_check_tray_id'),
    path('rec_ip_delete_batch/', RIPDeleteBatchAPIView.as_view(), name='rec_ip_delete_batch'),
    path('rec_IS_AcceptTable/', RIS_AcceptTable.as_view(), name='rec_IS_AcceptTable'),
    path('rec_IS_Completed_Table/', RIS_Completed_Table.as_view(), name='rec_IS_Completed_Table'),
    path('rec_get_rejection_details/', r_get_rejection_details, name='rec_get_rejection_details'),

    path('rec_ip_save_hold_unhold_reason/', RIPSaveHoldUnholdReasonAPIView.as_view(), name='rec_ip_save_hold_unhold_reason'),
    path('rec_verify_top_tray_qty/', RVerifyTopTrayQtyAPIView.as_view(), name='rec_verify_top_tray_qty'),

    path('rec_ip_tray_validate/', RIPTrayValidateAPIView.as_view(), name='rec_ip_tray_validate'),
    path('rec_ip_completed_tray_id_list/', RIPCompletedTrayIdListAPIView.as_view(), name='rec_ip_completed_tray_id_list'),

    path('rec_save_rejection_draft/', RSaveRejectionDraftAPIView.as_view(), name='rec_save_rejection_draft'),
    path('rec_get_rejection_draft/', r_get_rejection_draft, name='rec_get_rejection_draft'),
    path('rec_get_delink_tray_data/', r_get_delink_tray_data, name='rec_get_delink_tray_data'),
    path('rec_delink_check_tray_id/', r_delink_check_tray_id, name='rec_delink_check_tray_id'),
    path('rec_reject_check_tray_id_simple/', r_reject_check_tray_id_simple, name='rec_reject_check_tray_id_simple'),


    path('rec_complete_tray_validate/', RTrayValidate_Complete_APIView.as_view(), name='rec_complete_tray_validate'),
    path('rec_CompleteTable_tray_id_list/', RTrayIdList_Complete_APIView.as_view(), name='rec_CompleteTable_tray_id_list'),
    path('rec_get_shortage_rejections/', RGetShortageRejectionsView.as_view(), name='rec_get_shortage_rejections'),

    path('rec_delink_selected_trays/', r_delink_selected_trays, name='rec_delink_selected_trays'),

]