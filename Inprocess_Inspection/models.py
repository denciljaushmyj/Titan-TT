from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from modelmasterapp.models import TrayType

# Create your models here.

class InprocessInspectionTrayCapacity(models.Model):
    """
    Model to define custom tray capacities for Inprocess Inspection module
    This allows overriding the default ModelMaster tray capacities
    """
    tray_type = models.ForeignKey(
        TrayType, 
        on_delete=models.CASCADE, 
        help_text="Reference to tray type from ModelMaster"
    )
    custom_capacity = models.IntegerField(
        help_text="Custom capacity for this tray type in Inprocess Inspection"
    )
    is_active = models.BooleanField(
        default=True, 
        help_text="Whether this custom capacity is active"
    )
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="User who created this custom capacity"
    )
    
    class Meta:
        unique_together = ['tray_type', 'is_active']
        verbose_name = "Inprocess Inspection Tray Capacity"
        verbose_name_plural = "Inprocess Inspection Tray Capacities"
    
    def __str__(self):
        return f"{self.tray_type.tray_type} - {self.custom_capacity} (Custom)"
