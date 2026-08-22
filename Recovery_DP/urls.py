from django.urls import path
from .views import *

urlpatterns = [
    path('rec_bulk_upload/', RBulkUploadView.as_view(), name='rec_bulk_upload'),
    path('rec_bulk_upload/preview/', RBulkUploadPreviewView.as_view(), name='rec_bulk_upload_preview'),

    # Auto-fetch APIs for Single Upload
    path('rec_get_plating_colour/', RGetPlatingColourAPIView.as_view(), name='rec_get_plating_colour'),
    path('rec_get_categories/', RGetCategoriesAPIView.as_view(), name='rec_get_categories'),
    path('rec_get_locations/', RGetLocationsAPIView.as_view(), name='rec_get_locations'),


    path('rec_dp_pick_table/', RDayPlanningPickTableAPIView.as_view(), name='rec_dp_pick_table'),
    path('rec_tray_scan/', RTrayIdScanAPIView.as_view(), name='rec_tray_scan'),
    path('rec_top_tray_scan/', RTopTrayScanAPIView.as_view(), name='rec_top_tray_scan'),
    path('rec_validate_top_tray/', RValidateTopTrayAPIView.as_view(), name='rec_validate_top_tray'),

    path('rec_tray_id_list/', RTrayIdListAPIView.as_view(), name='rec_tray_id_list'),
    path('rec_tray_id_unique_check/', RTrayIdUniqueCheckAPIView.as_view(), name='rec_tray_id_unique_check'),
    path('rec_draft_tray/', RDraftTrayIdAPIView.as_view(), name='rec_draft_tray'),
    path('rec_draft_tray_id_list/', RDraftTrayIdListAPIView.as_view(), name='rec_draft_tray_id_list'),

    path('rec_dp_completed_table/', RDPCompletedTableView.as_view(), name='rec_dp_completed_table'),  # <-- Add this
    path('rec_completed_tray_id_list/', RCompletedTrayIdListAPIView.as_view(), name='rec_completed_tray_id_list'),
    path('rec_tray_validate/', RTrayValidateAPIView.as_view(), name='rec_tray_validate'),


    path('rec_delete_batch/', RDeleteBatchAPIView.as_view(), name='rec_delete_batch'),
    path('rec_update_batch_quantity_and_color/', RUpdateBatchQuantityAndColorAPIView.as_view(), name='rec_update_batch_quantity_and_color'),
    path('rec_get_plating_colors/', RGetPlatingColorsAPIView.as_view(), name='rec_get_plating_colors'),
    path('rec_save_dp_pick_remark/', RSaveDPPickRemarkAPIView.as_view(), name='rec_save_dp_pick_remark'),
    path('rec_verify_top_tray_qty/', RVerifyTopTrayQtyAPIView.as_view(), name='rec_verify_top_tray_qty'),
    path('rec_save_hold_unhold_reason/', RSaveHoldUnholdReasonAPIView.as_view(), name='rec_save_hold_unhold_reason'),

    path('rec_tray_auto_save/', RTrayAutoSaveAPIView.as_view(), name='rec_tray_auto_save'),
    path('rec_tray_auto_save_cleanup/', RTrayAutoSaveCleanupAPIView.as_view(), name='rec_tray_auto_save_cleanup'),

]