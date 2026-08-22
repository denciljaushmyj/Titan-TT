from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from modelmasterapp.models import ModelMasterCreation

# Create your models here.

class DPQuickHelp(models.Model):
    """
    Day Planning Quick Help Guidelines
    Stores Do's and Don'ts for the Quick Help panel
    Admins can add, edit, delete items in real-time from Django admin
    """
    CATEGORY_CHOICES = [
        ('do', "Do's"),
        ('dont', "Don'ts"),
    ]
    
    title = models.CharField(max_length=150, help_text="Title of the guideline (e.g., 'Verify Tray Condition')")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, help_text="Is this a Do or Don't?")
    description = models.TextField(help_text="Detailed description/instruction")
    icon_code = models.CharField(max_length=10, default="✓", help_text="Icon/symbol (✓ for do, ✗ for dont, or emoji)")
    order = models.PositiveIntegerField(default=0, help_text="Display order (0=first)")
    is_active = models.BooleanField(default=True, help_text="Show/hide this guideline")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='dpquickhelp_created')
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.CharField(max_length=250, null=True, blank=True, help_text="Internal notes")

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"

    class Meta:
        verbose_name = "DP Quick Help Guideline"
        verbose_name_plural = "DP Quick Help Guidelines"
        ordering = ['category', 'order', 'created_at']
        indexes = [
            models.Index(fields=['category', 'is_active']),
        ]

class DPTrayId_History(models.Model):
    """
    TrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(ModelMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    top_tray = models.BooleanField(default=False)

    delink_tray = models.BooleanField(default=False, help_text="Is tray delinked")
    delink_tray_qty = models.CharField(max_length=50, null=True, blank=True, help_text="Delinked quantity")
    
    IP_tray_verified= models.BooleanField(default=False, help_text="Is tray verified in IP")
    
    rejected_tray= models.BooleanField(default=False, help_text="Is tray rejected")

    new_tray=models.BooleanField(default=True, help_text="Is tray new")
    
    # Tray configuration fields (filled by admin)
    tray_type = models.CharField(max_length=50, null=True, blank=True, help_text="Type of tray (Jumbo, Normal, etc.) - filled by admin")
    tray_capacity = models.IntegerField(null=True, blank=True, help_text="Capacity of this specific tray - filled by admin")
    
    # NEW FIELD: Scanned status tracking
    scanned = models.BooleanField(default=False, help_text="Indicates if the tray has been scanned/used")

    def __str__(self):
        return f"{self.tray_id} - {self.lot_id} - {self.tray_quantity}"

    @property
    def is_available_for_scanning(self):
        """
        Check if tray is available for scanning
        Available if: not scanned OR delinked (can be reused)
        """
        return not self.scanned or self.delink_tray

    @property
    def status_display(self):
        """Get human-readable status"""
        if self.delink_tray:
            return "Delinked (Reusable)"
        elif self.scanned:
            return "Already Scanned"
        elif self.batch_id:
            return "In Use"
        else:
            return "Available"

    class Meta:
        verbose_name = "DPTray History ID"
        verbose_name_plural = "DPTray History IDs"
