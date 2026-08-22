from django.urls import path
from django.shortcuts import redirect
from modelmasterapp.views import *
from modelmasterapp import rowlock_views


def legacy_login_redirect(request):
    return redirect('login')

urlpatterns = [
    path('', legacy_login_redirect, name='legacy-login-api'),

    # Centralized pick-row lock endpoints (shared by all modules).
    path('rowlock/acquire/', rowlock_views.acquire, name='rowlock_acquire'),
    path('rowlock/heartbeat/', rowlock_views.heartbeat, name='rowlock_heartbeat'),
    path('rowlock/release/', rowlock_views.release, name='rowlock_release'),
    path('rowlock/status/', rowlock_views.status, name='rowlock_status'),
    path('base/', BaseAPIView.as_view(), name='base-api'),
    path('api/get-lot-by-model/', GetLotByModelAPIView.as_view(), name='get-lot-by-model'),
    path('logout/', logout_view, name='logout'),
    path('delete_all/', delete_all_tables, name='delete_all_tables'),
    path('get-plating-images/', get_plating_images, name='get_plating_images'),

]
