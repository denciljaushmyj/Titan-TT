from django.urls import path
from django.views.generic import RedirectView
from .views import (
    NA_PickTableView,
    NACompletedView,
    na_action,
    na_completed_tray_list,
    na_completed_tray_validate,
    na_delete_lot,
    na_delink_selected_trays,
    na_hold_unhold,
    na_toggle_verified,
)

urlpatterns = [
    path('NA_PickTable/', NA_PickTableView.as_view(), name='NA_PickTable'),
    path('NA_Completed/', NACompletedView.as_view(), name='NA_Completed'),
    # Action APIs
    path('api/toggle-verified/', na_toggle_verified, name='na_toggle_verified'),
    path('api/action/', na_action, name='na_action'),
    path('api/hold-unhold/', na_hold_unhold, name='na_hold_unhold'),
    path('api/delete-lot/', na_delete_lot, name='na_delete_lot'),
    path('nickel_audit_delink_selected_trays/', na_delink_selected_trays, name='na_delink_selected_trays'),
    path('pick_CompleteTable_tray_id_list/', na_completed_tray_list, name='na_completed_tray_list'),
    path('pick_complete_tray_validate/', na_completed_tray_validate, name='na_completed_tray_validate'),
    # Backward compat redirect
    path('NA_Inspection/', RedirectView.as_view(pattern_name='NA_PickTable', permanent=True)),
]