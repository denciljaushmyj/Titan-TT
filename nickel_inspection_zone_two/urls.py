from django.urls import path
from .views import NQ_Zone_PickTableView, NQ_Zone_CompletedView, NQ_Zone_RejectTableView
from Nickel_Inspection.views import nq_toggle_verified, nq_action, nq_hold_unhold, nq_completed_tray_list

urlpatterns = [
    path('NQ_Zone_PickTable/', NQ_Zone_PickTableView.as_view(), name='NQ_Zone_PickTable'),
    path('NQ_Zone_Completed/', NQ_Zone_CompletedView.as_view(), name='NQ_Zone_Completed'),
    path('nq_zone_rejection_table/', NQ_Zone_RejectTableView.as_view(), name='nq_zone_rejection_table'),
    path('api/toggle-verified/', nq_toggle_verified, name='nq_zone_toggle_verified'),
    path('api/action/', nq_action, name='nq_zone_action'),
    path('api/hold-unhold/', nq_hold_unhold, name='nq_zone_hold_unhold'),
    path('nickel_CompleteTable_tray_id_list/', nq_completed_tray_list, name='nq_zone_completed_tray_list'),
]