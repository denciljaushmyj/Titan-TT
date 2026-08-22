from django.urls import path

from . import views

app_name = 'sop_management'

urlpatterns = [
    # Page
    path('', views.SOPManagementPageView.as_view(), name='sop_management_page'),

    # User-facing read APIs
    path('api/sop/modules/', views.SOPModuleListAPIView.as_view(), name='sop_modules'),
    path('api/sop/file/<int:pk>/', views.SOPFileServeAPIView.as_view(), name='sop_file_serve'),
    path('api/sop/<int:module_id>/', views.SOPActiveByModuleAPIView.as_view(), name='sop_active_by_module'),

    # Admin CRUD APIs
    path('api/admin/sop/list/', views.SOPAdminListAPIView.as_view(), name='sop_admin_list'),
    path('api/admin/sop/upload/', views.SOPUploadAPIView.as_view(), name='sop_admin_upload'),
    path('api/admin/sop/update/<int:pk>/', views.SOPUpdateAPIView.as_view(), name='sop_admin_update'),
    path('api/admin/sop/delete/<int:pk>/', views.SOPDeleteAPIView.as_view(), name='sop_admin_delete'),
]
