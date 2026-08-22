"""
SOP Management Selectors — DB read-only layer.

All queryset building and data-fetching logic lives here.
Views call these functions — no queryset logic directly in views.

Rule: NO writes here. Only reads.
"""
import logging

from django.db.models import Q

from .models import SOPMaster, SOPModule

logger = logging.getLogger(__name__)


def get_active_sop_modules():
    """Modules shown in the user-facing SOP picker (active only)."""
    return SOPModule.objects.filter(is_active=True).order_by('sort_order', 'name')


def get_all_sop_modules():
    """Full module list for the admin upload/edit form's Module dropdown."""
    return SOPModule.objects.all().order_by('sort_order', 'name')


def get_active_sop_for_module(module_id):
    """The single currently-active, non-deleted SOP for a module, or None."""
    return (
        SOPMaster.objects
        .select_related('module', 'uploaded_by')
        .filter(module_id=module_id, is_active=True, is_deleted=False)
        .first()
    )


def get_sop_by_id(sop_id):
    return (
        SOPMaster.objects
        .select_related('module', 'uploaded_by', 'updated_by')
        .filter(pk=sop_id, is_deleted=False)
        .first()
    )


def get_admin_sop_list(search=None, module_id=None, status=None):
    """
    Base queryset for the admin SOP list screen.

    status: 'active' | 'inactive' | None (all).
    search: matches sop_title, version, or module name (icontains).
    """
    queryset = (
        SOPMaster.objects
        .select_related('module', 'uploaded_by', 'updated_by')
        .filter(is_deleted=False)
    )

    if module_id:
        queryset = queryset.filter(module_id=module_id)

    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    if search:
        queryset = queryset.filter(
            Q(sop_title__icontains=search)
            | Q(version__icontains=search)
            | Q(module__name__icontains=search)
        )

    return queryset.order_by('-uploaded_date')


def get_other_active_sops_for_module(module_id, exclude_id=None):
    """Active SOPs for a module other than exclude_id — used to archive on activate."""
    queryset = SOPMaster.objects.filter(module_id=module_id, is_active=True, is_deleted=False)
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset
