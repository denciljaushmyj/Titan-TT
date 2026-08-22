from django.urls import path
from .views import *

app_name = 'reports_module'

urlpatterns = [
  
    path('reports/', ReportsView.as_view(), name='reports'),
    path('download_report/', download_report, name='download_report'),
    path('consolidated_report/preview/', consolidated_report_preview, name='consolidated_report_preview'),
    path('consolidated_report/download/', consolidated_report_download, name='consolidated_report_download'),
    path('plating_stock_autocomplete/', plating_stock_autocomplete, name='plating_stock_autocomplete'),

]



