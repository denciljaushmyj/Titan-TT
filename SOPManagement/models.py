import os
import uuid

from django.contrib.auth.models import User
from django.db import models


def sop_file_upload_path(instance, filename):
    """
    Build the storage path for an uploaded SOP document.

    The client-supplied filename is discarded (only the extension is kept)
    so the on-disk name is opaque and never attacker/user controlled, same
    pattern as modelmasterapp.models.model_image_upload_path. The original
    filename is preserved separately on SOPMaster.file_name for display.

    Result: sop_documents/<uuid4hex>.pdf
    """
    ext = os.path.splitext(filename)[1].lower()
    return f'sop_documents/{uuid.uuid4().hex}{ext}'


class SOPModule(models.Model):
    """
    Reference list of manufacturing process modules an SOP can be assigned
    to (Day Planning, Input Screening, Brass QC, ...). Kept as its own
    lightweight master table rather than reusing adminportal.Module, which
    represents fine-grained sidebar/page entries (e.g. "DP Pick Table") for
    role-based menu access control — a different granularity than the
    process-level module an SOP document applies to.
    """
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "SOP Module"
        verbose_name_plural = "SOP Modules"

    def __str__(self):
        return self.name


class SOPMaster(models.Model):
    """
    One row per uploaded SOP document/version. Only one row per module may
    have is_active=True at a time (enforced in SOPManagement.services, not
    a DB constraint, because activating a new version must archive the
    previous one rather than reject the write).
    """
    module = models.ForeignKey(SOPModule, on_delete=models.PROTECT, related_name='sops')
    sop_title = models.CharField(max_length=200)
    version = models.CharField(max_length=20)
    description = models.TextField(blank=True, default='')
    file = models.FileField(upload_to=sop_file_upload_path, max_length=500)
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_size = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sop_uploads'
    )
    uploaded_date = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sop_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-uploaded_date']
        indexes = [
            models.Index(fields=['module', 'is_active', 'is_deleted'], name='sop_module_active_idx'),
            models.Index(fields=['uploaded_date'], name='sop_uploaded_date_idx'),
        ]
        verbose_name = "SOP Master"
        verbose_name_plural = "SOP Master"

    def __str__(self):
        return f"{self.module.name} - {self.sop_title} (v{self.version})"
