from django.urls import path
from django.views.generic import RedirectView
from .views import NA_Zone_PickTableView, NA_Zone_CompletedView
from Nickel_Audit.views import (
    na_action,
    na_completed_tray_list,
    na_completed_tray_validate,
    na_delete_lot,
    na_delink_selected_trays,
    na_hold_unhold,
    na_toggle_verified,
)

urlpatterns = [
    path('NA_Zone_PickTable/', NA_Zone_PickTableView.as_view(), name='NA_Zone_PickTable'),
    path('NA_Zone_Completed/', NA_Zone_CompletedView.as_view(), name='NA_Zone_Completed'),
    # Action APIs (reuse Zone 1 views)
    path('api/toggle-verified/', na_toggle_verified, name='na_zone_toggle_verified'),
    path('api/action/', na_action, name='na_zone_action'),
    path('api/hold-unhold/', na_hold_unhold, name='na_zone_hold_unhold'),
    path('api/delete-lot/', na_delete_lot, name='na_zone_delete_lot'),
    path('nickel_audit_delink_selected_trays/', na_delink_selected_trays, name='na_zone_delink_selected_trays'),
    path('pick_CompleteTable_tray_id_list/', na_completed_tray_list, name='na_zone_completed_tray_list'),
    path('pick_complete_tray_validate/', na_completed_tray_validate, name='na_zone_completed_tray_validate'),
    # Backward compat redirect
    path('NA_Zone_Inspection/', RedirectView.as_view(pattern_name='NA_Zone_PickTable', permanent=True)),
]