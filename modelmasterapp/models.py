from django.db import models
from django.utils import timezone
from django.db.models import F
from django.core.exceptions import ValidationError
import datetime
import os
import uuid
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.db.models import JSONField
from django.contrib.postgres.fields import ArrayField
from IQF.models import IQF_Rejection_ReasonStore, IQF_Accepted_TrayScan, IQF_Accepted_TrayID_Store, IQF_Rejected_TrayScan, IQF_Rejection_Table 
from InputScreening.models import IP_RejectionGroup, IP_Accepted_TrayScan, IP_Rejection_ReasonStore, IP_Rejected_TrayScan ,IP_Accepted_TrayID_Store
from Jig_Loading.models import *
from Brass_QC.models import Brass_QC_Rejection_Table, Brass_QC_Rejection_ReasonStore, Brass_QC_Rejected_TrayScan, Brass_Qc_Accepted_TrayScan, Brass_Qc_Accepted_TrayID_Store
from modelmasterapp.tray_code_mapping import TRAY_CODE_CHOICES


from django.db import models
from django.contrib.auth.models import User

# Model to track row access locks
class RowAccessLock(models.Model):
    batch_id = models.CharField(max_length=100, db_index=True)
    lot_id = models.CharField(max_length=100, db_index=True)
    accessed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('batch_id', 'lot_id')


class PickRowLock(models.Model):
    """
    Centralized, database-backed pessimistic lock for pick-table rows across
    every processing module (Day Planning -> Spider Spindle Z2).

    Design notes:
    - `module` + `lock_key` uniquely identify a row. `lock_key` is normally the
      lot_id (falls back to batch_id / jig id for modules that key on those).
    - Ownership is enforced at the DB level. Acquire/refresh/steal all run inside
      transaction.atomic() + select_for_update() in
      modelmasterapp.rowlock_service, so two simultaneous requests can never both
      win the same row.
    - `heartbeat_at` is refreshed by the owner via a lightweight heartbeat. A lock
      whose heartbeat is older than settings.PICK_ROW_LOCK_TTL_SECONDS is treated
      as stale (abandoned tab / browser close / crash) and may be reclaimed. This
      guarantees no permanent locks without any cron/background job.
    """
    module = models.CharField(max_length=50, db_index=True)
    lock_key = models.CharField(max_length=120, db_index=True)
    locked_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='pick_row_locks'
    )
    # Snapshot of the owner's display name so status responses never do an extra
    # user join and survive a later username change for audit display.
    locked_by_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Pick Row Lock"
        verbose_name_plural = "Pick Row Locks"
        unique_together = ('module', 'lock_key')
        indexes = [
            models.Index(fields=['module', 'lock_key'], name='pickrowlock_mod_key_idx'),
            models.Index(fields=['heartbeat_at'], name='pickrowlock_heartbeat_idx'),
        ]

    def __str__(self):
        return f"{self.module}:{self.lock_key} -> {self.locked_by_name or self.locked_by_id}"


def model_image_upload_path(instance, filename):
    """
    Build the storage path for an uploaded ModelImage file.

    Task 5 hardening: the client-supplied filename is never used as the
    on-disk name. Only the extension is kept (it has already been checked
    against the allowlist and against the detected file signature by
    ModelImageSerializer.validate_master_image() in
    adminportal/serializers.py before this function ever runs), and the
    base name is replaced with a UUID4 hex string so the stored filename
    is fully opaque and not attacker/user controlled.

    Result: model_images/<uuid4hex>.<ext>
    e.g.   model_images/9f1c52de9f7a4aa9854c72564a09a671.png

    This function only affects new uploads. Existing ModelImage rows keep
    the path already stored in the database and continue to resolve via
    MEDIA_ROOT/MEDIA_URL exactly as before.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f'model_images/{uuid.uuid4().hex}{ext}'


# API for Model Images Masters
class ModelImage(models.Model):
  #give master_image field for mulitple image slection
    master_image = models.ImageField(upload_to=model_image_upload_path)
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Master_Image {self.id}"
    
class PolishFinishType(models.Model):
    polish_finish = models.CharField(max_length=255, unique=True, help_text="Type of polish finish")
    polish_internal = models.CharField(
        max_length=255,
        unique=True,
        default="DefaultInternal",
        help_text="Internal name of the Polish Finish"
    )
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


    def __str__(self):
        return self.polish_finish 
    
class Plating_Color(models.Model):
    #need choices for plating color field -dropdown field
    plating_color = models.CharField(max_length=255, unique=True, help_text="Plating color")
    plating_color_internal = models.CharField(
        max_length=10, 
        help_text="Short internal code used in stock number (e.g., B for Black)", 
    )
    jig_unload_zone_1 = models.BooleanField(default=False, help_text="Indicates if Jig Unload Zone 1 is active")
    jig_unload_zone_2 = models.BooleanField(default=False, help_text="Indicates if Jig Unload Zone 2 is active")
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.plating_color
    
        
class Version(models.Model):
    version_name = models.CharField(max_length=255, unique=True, help_text="Version name")
    version_internal = models.CharField(max_length=255, unique=True,null=True,blank=True, help_text="Version Internal")
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


    def __str__(self):
        return self.version_name
    
class TrayType(models.Model):
    tray_type = models.CharField(max_length=255, unique=True, help_text="Type of tray")
    tray_capacity = models.IntegerField(help_text="Number of watches the tray can hold")  
    tray_color = models.CharField(max_length=255, help_text="Color of the tray",blank=True, null=True)  
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.tray_type
    
class Vendor(models.Model):
    vendor_name = models.CharField(max_length=255, unique=True, help_text="Name of the vendor")
    vendor_internal = models.CharField(max_length=255, unique=True, help_text="Internal name of the vendor")
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.vendor_name

class Location(models.Model):
    location_name = models.CharField(max_length=255, unique=True, help_text="Name of the location")
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.location_name
    
class Category(models.Model):
    category_name = models.CharField(max_length=255, unique=True, help_text="Name of the location")
    date_time = models.DateTimeField(default=timezone.now)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.category_name
    
    
class ModelMaster(models.Model):
    # Assuming this model holds the reference data for dropdowns and auto-fetch fields
    model_no = models.CharField(max_length=100)
    polish_finish = models.ForeignKey(PolishFinishType, on_delete=models.SET_NULL, null=True, blank=True)
    ep_bath_type = models.CharField(max_length=100)
    tray_type = models.ForeignKey(TrayType, on_delete=models.SET_NULL, null=True, blank=True)
    tray_capacity = models.IntegerField(null=True, blank=True)
    tray_code = models.CharField(
        max_length=5,
        choices=TRAY_CODE_CHOICES,
        null=True,
        blank=True,
        help_text="Nickel tray code for this model (NR, ND, NB, NL, JR, JD, JB, JL)",
    )
    images = models.ManyToManyField(ModelImage, blank=True)  # Allows multiple images
    vendor_internal = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.CharField(max_length=100,null=True, blank=True)
    gender = models.CharField(max_length=50,null=True, blank=True)
    wiping_required = models.BooleanField(default=False)
    date_time = models.DateTimeField(default=timezone.now)
    version = models.TextField()
    plating_stk_no=models.CharField(max_length=50,null=True, blank=True)
    plating_color_code = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color code uniquely assigned per Plating Stk No, used for model-presence circles",
    )
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


    def __str__(self):
        if self.model_no and self.plating_stk_no:
            return f"{self.model_no} ({self.plating_stk_no})"
        elif self.model_no:
            return self.model_no
        elif self.plating_stk_no:
            return self.plating_stk_no
        else:
            return f"ModelMaster ID: {self.id}" 


class ModelVersionComparison(models.Model):
    model_number = models.CharField(
        max_length=100
    )

    version = models.CharField(
        max_length=20,
        blank=True,
        default="ALL"
    )

    title = models.CharField(
        max_length=200,
        blank=True
    )

    comparison_image = models.ImageField(
        upload_to="model_version_comparisons/",
        blank=True,
        null=True
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    version_info = models.JSONField(
        default=dict,
        blank=True
    )

    o_ring_pocket = models.CharField(
        max_length=10,
        blank=True,
        null=True
    )

    dial_slant_finish = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    thickness = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True
    )

    bcb_to_lug_bottom = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True
    )

    dial_slant_angle = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True
    )

    dial_slant_height = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["model_number", "version"],
                name="unique_model_version_comparison"
            )
        ]

    def __str__(self):
        return f"{self.model_number} - {self.version}"


class ModelVersionComparisonImage(models.Model):
    comparison = models.ForeignKey(
        ModelVersionComparison,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="model_version_comparisons/"
    )

    original_filename = models.CharField(
        max_length=255,
        blank=True
    )

    display_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.comparison} image {self.display_order}"
      
        
class LookLikeModel(models.Model):
    """
    Model to store 'Look Like' relationships between plating stock numbers.
    """
    plating_stk_no = models.ManyToManyField(
        ModelMaster,
        related_name='look_like_models',
        verbose_name="Plating Stock Numbers",
        help_text="Select multiple plating stock numbers from ModelMaster"
    )

    same_plating_stk_no = models.ForeignKey(
        ModelMaster,
        on_delete=models.CASCADE,
        related_name='same_plating_stk_no_references',
        verbose_name="Same Plating Stock Number",
        help_text="Select single plating stock number for same model reference"
    )

    text = models.TextField(
        verbose_name="Look Like Model",
        help_text="Description of what this model looks like"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Look Like Model"
        verbose_name_plural = "Look Like Models"
        ordering = ['-created_at']

    def __str__(self):
        # Show only plating_stk_no for same_plating_stk_no
        return f"Look Like: {self.text[:50]}... (Same: {self.same_plating_stk_no.plating_stk_no})"

    def get_plating_stk_no_list(self):
        """Helper method to get comma-separated plating_stk_no values"""
        return ", ".join([model.plating_stk_no for model in self.plating_stk_no.all() if model.plating_stk_no])

    def get_model_count(self):
        """Helper method to get count of associated models"""
        return self.plating_stk_no.count()

class ModelMasterCreation(models.Model):
    
    #unique_id = models.CharField(max_length=100, unique=True,null=True, blank=True) #not in use
    batch_id = models.CharField(max_length=50, unique=True)
    lot_id = models.CharField(max_length=100, unique=True, null=True, blank=True)  # <== ADD THIS LINE
    model_stock_no = models.ForeignKey(ModelMaster, related_name='model_stock_no', on_delete=models.CASCADE)
    polish_finish = models.CharField(max_length=100)
    ep_bath_type = models.CharField(max_length=100)
    plating_color=models.CharField(max_length=100,null=True,blank=True)
    tray_type = models.CharField(max_length=100)
    tray_capacity = models.IntegerField(null=True, blank=True)
    images = models.ManyToManyField(ModelImage, blank=True)  # Store multiple images
    date_time = models.DateTimeField(default=timezone.now)
    version = models.ForeignKey(Version, on_delete=models.CASCADE, help_text="Version")
    total_batch_quantity = models.IntegerField()  
    initial_batch_quantity = models.IntegerField(default=0) #not in use
    current_batch_quantity = models.IntegerField(default=0)  # not in use
    no_of_trays = models.IntegerField(null=True, blank=True)  # Calculated field
    vendor_internal = models.CharField(max_length=100,null=True, blank=True)
    sequence_number = models.IntegerField(default=0)  # Add this field
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)  # Allow null values
    Moved_to_D_Picker = models.BooleanField(default=False, help_text="Moved to D Picker")
    top_tray_qty_verified = models.BooleanField(default=False, help_text="On Hold Picking")
    verified_tray_qty=models.IntegerField(default=0, help_text="Verified Tray Quantity")
    top_tray_qty_modify=models.IntegerField(default=0, help_text="Top Tray Quantity Modified")
    Draft_Saved=models.BooleanField(default=False,help_text="Draft Save")
    dp_pick_remarks=models.CharField(max_length=100,null=True, blank=True)
    category=models.CharField(max_length=100, null=True, blank=True, help_text="Category of the model")
    plating_stk_no=models.CharField(max_length=100, null=True, blank=True, help_text="Plating Stock Number")
    polishing_stk_no=models.CharField(max_length=100,null=True, blank=True)
    holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Reason for holding the batch")  
    release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="Reason for releasing the batch")
    hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold")
    release_lot =models.BooleanField(default=False)
    previous_lot_status = models.CharField(max_length=50, blank=True, null=True)
    changes = models.CharField(max_length=255, blank=True, null=True, default="Outer Groove")
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    UPLOAD_TYPE_CHOICES = [
        ('day_planning', 'Day Planning'),
        ('recovery', 'Recovery Upload'),
    ]
    upload_type = models.CharField(
        max_length=20,
        choices=UPLOAD_TYPE_CHOICES,
        default='day_planning',
        verbose_name="Type of Input",
        help_text="Source of upload: Day Planning or Recovery Upload",
    )

    # ═══ Centralized Lot Status (lot_status app) ═══
    # Single unified status field reused across every production module.
    # Do NOT create parallel/per-module status columns — call
    # lot_status.services.transition_lot_status() to change this.
    UNIFIED_STATUS_CHOICES = [
        ('YET_TO_START', 'Yet to Start'),
        ('IN_PROGRESS', 'In Progress'),
        ('DRAFT', 'Draft'),
        ('RELEASED', 'Released'),
    ]
    unified_status = models.CharField(
        max_length=20,
        choices=UNIFIED_STATUS_CHOICES,
        default='YET_TO_START',
        db_index=True,
        help_text="Centralized lot status (Yet to Start -> In Progress -> Draft -> Released), managed only via lot_status.services.transition_lot_status()",
    )
    unified_status_module = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Which module last changed unified_status (e.g. DayPlanning, InputScreening)",
    )
    unified_status_updated_at = models.DateTimeField(null=True, blank=True)
    unified_status_updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='unified_status_events',
    )
    unified_status_reason = models.CharField(max_length=255, null=True, blank=True)

    def save(self, *args, **kwargs):

        if not self.pk:  # Only set the sequence number for new instances
            last_batch = ModelMasterCreation.objects.order_by('-sequence_number').first()
            self.sequence_number = 1 if not last_batch else last_batch.sequence_number + 1
        
        # Fetch related data from ModelMaster
        model_data = self.model_stock_no
        
        
        self.ep_bath_type = model_data.ep_bath_type
        
        # FIXED: Convert tray_type ForeignKey to string
        if model_data.tray_type:
            self.tray_type = model_data.tray_type.tray_type  # Use the actual field value
        else:
            self.tray_type = ""
        
        self.tray_capacity = model_data.tray_capacity

        super().save(*args, **kwargs)
        self.images.set(model_data.images.all())


    def __str__(self):
        return f"{self.model_stock_no} - {self.batch_id}"

        
class TrayId(models.Model):
    """
    TrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, unique=True, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(ModelMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    top_tray = models.BooleanField(default=False)
    ip_top_tray = models.BooleanField(default=False)
    ip_top_tray_qty= models.IntegerField(default=0, help_text="IP Top Tray Quantity")

    brass_top_tray = models.BooleanField(default=False)
    brass_top_tray_qty= models.IntegerField(default=0, help_text="Brass Top Tray Quantity")

    iqf_top_tray = models.BooleanField(default=False)
    iqf_top_tray_qty= models.IntegerField(default=0, help_text="IQF Top Tray Quantity")


    delink_tray = models.BooleanField(default=False, help_text="Is tray delinked")
    delink_tray_qty = models.CharField(max_length=50, null=True, blank=True, help_text="Delinked quantity")
    
    IP_tray_verified= models.BooleanField(default=False, help_text="Is tray verified in IP")
    
    rejected_tray= models.BooleanField(default=False, help_text="Is tray rejected")
    brass_rejected_tray= models.BooleanField(default=False, help_text="Is brass tray rejected")

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
        Available if: new OR delinked (can be reused)
        """
        return self.new_tray or self.delink_tray

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
        verbose_name = "Tray ID"
        verbose_name_plural = "Tray IDs"
       
       
class DraftTrayId(models.Model):
    """
    TrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, blank=True, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(ModelMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
    position = models.IntegerField(
        help_text="Position/slot number in the tray scan grid",
        null=True,
        blank=True,
        default=None
    )    
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # ✅ NEW: Add delink fields
    delink_tray = models.BooleanField(default=False, help_text="Is tray delinked")
    delink_tray_qty = models.CharField(max_length=50, null=True, blank=True, help_text="Delinked quantity")
    
    class Meta:
        unique_together = ('batch_id', 'position')
        constraints = [
            models.UniqueConstraint(
                fields=['batch_id', 'tray_id'],
                condition=models.Q(tray_id__gt=''),
                name='unique_non_empty_tray_id_per_batch'
            )
        ]
    
    def __str__(self):
        return f"{self.tray_id or 'Empty'} - Position {self.position} - {self.tray_quantity}"  


class TotalStockModel(models.Model):
    """
    This model is for saving overall stock in Day Planning operation form.
  
    """
    batch_id = models.ForeignKey(ModelMasterCreation, on_delete=models.CASCADE, null=True, blank=True)

    model_stock_no = models.ForeignKey(ModelMaster, on_delete=models.CASCADE, help_text="Model Stock Number")
    version = models.ForeignKey(Version, on_delete=models.CASCADE, help_text="Version")
    total_stock = models.IntegerField(help_text="Total stock quantity")
    polish_finish = models.ForeignKey(PolishFinishType, on_delete=models.SET_NULL, null=True, blank=True, help_text="Polish Finish")

    plating_color = models.ForeignKey(Plating_Color, on_delete=models.SET_NULL, null=True, blank=True, help_text="Plating Color")
    location = models.ManyToManyField(Location, blank=True, help_text="Multiple Locations")
    lot_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="Lot ID")
    created_at = models.DateTimeField(default=now, help_text="Timestamp of the record")
    # day planning missing qty in day planning pick table
    dp_missing_qty = models.IntegerField(default=0, help_text="Missing quantity in day planning")
    dp_physical_qty = models.IntegerField(help_text="Original physical quantity", default=0)  # New field
    dp_physical_qty_edited = models.BooleanField(default=False, help_text="Qunatity Edited in IP")
    cumulative_edit_difference = models.IntegerField(default=0)  # Total edit amount
    original_tray_qty = models.IntegerField(null=True, blank=True)  # Original value
    
    brass_missing_qty= models.IntegerField(default=0, help_text="Missing quantity in Brass QC")
    brass_physical_qty= models.IntegerField(help_text="Original physical quantity in Brass QC", default=0)  # New field
    brass_physical_qty_edited = models.BooleanField(default=False, help_text="Qunatity Edited in Brass")

    brass_audit_missing_qty = models.IntegerField(default=0, help_text="Missing quantity in Brass Audit")
    brass_audit_physical_qty = models.IntegerField(help_text="Original physical quantity in Brass Audit", default=0)
    brass_audit_physical_qty_edited = models.BooleanField(default=False, help_text="Qunatity Edited in Brass")

    iqf_missing_qty = models.IntegerField(default=0, help_text="Missing quantity in IQF")
    iqf_physical_qty = models.IntegerField(help_text="Original physical quantity in IQF", default=0)  # New field
    iqf_physical_qty_edited= models.BooleanField(default=False, help_text="Qunatity Edited in IQF")
    
    jig_physical_qty = models.IntegerField(help_text="Original physical quantity in JIG", default=0)  # New field
    jig_physical_qty_edited = models.BooleanField(default=False, help_text="Qunatity Edited in JIG")    
    
    # New fields for process tracking
    last_process_date_time = models.DateTimeField(null=True, blank=True, help_text="Last Process Date/Time")
    last_process_module = models.CharField(max_length=255, null=True, blank=True, help_text="Last Process Module")
    next_process_module = models.CharField(max_length=255, null=True, blank=True, help_text="Next Process Module")



    bq_last_process_date_time = models.DateTimeField(null=True, blank=True, help_text="Last Process Date/Time")
    iqf_last_process_date_time = models.DateTimeField(null=True, blank=True, help_text="Last Process Date/Time")
    brass_audit_last_process_date_time = models.DateTimeField(null=True, blank=True, help_text="Last Process Date/Time")

    #IP Module accept and rejection
    total_IP_accpeted_quantity = models.IntegerField(default=0, help_text="Total accepted quantity")
    total_qty_after_rejection_IP = models.IntegerField(default=0, help_text="Total rejected quantity")
    
    #Brass QC Module accept and rejection
    brass_qc_accepted_qty = models.IntegerField(default=0, help_text="Brass QC Accepted Quantity")  # New field
    brass_qc_after_rejection_qty = models.IntegerField(default=0, help_text="Brass QC Rejected Quantity")  # New field
    
    #IQF Module accept and rejection
    iqf_accept_qty_after_accept_ftn = models.IntegerField(default=0, help_text="IQF Accepted Quantity")  # New field
    iqf_accepted_qty = models.IntegerField(default=0, help_text="IQF Accepted Quantity")  # New field
    iqf_after_rejection_qty = models.IntegerField(default=0, help_text="IQF Rejected Quantity")  # New field
    
    #IP Verification and tray_scan
    tray_scan_status = models.BooleanField(default=False, help_text="Tray scan status")
    ip_person_qty_verified = models.BooleanField(default=False, help_text="IP Person Quantity Verified")  # New field
    draft_tray_verify = models.BooleanField(default=False, help_text="Draft Tray Verified")  # After Verify the qty - Based on this show Draft mode
    accepted_Ip_stock = models.BooleanField(default=False, help_text="Accepted IP Stock")  # New fiel
    few_cases_accepted_Ip_stock = models.BooleanField(default=False, help_text="Few Accepted IP Stock")  # New field
    rejected_ip_stock = models.BooleanField(default=False, help_text="Rejected IP Stock")  # New field
    wiping_status = models.BooleanField(default=False, help_text="Wiping Status")  # New field
    IP_pick_remarks=models.CharField(max_length=100, null=True, blank=True, help_text="IP Pick Remarks")
    Bq_pick_remarks= models.CharField(max_length=100, null=True, blank=True, help_text="BQ Pick Remarks")  # New field
    BA_pick_remarks= models.CharField(max_length=100, null=True, blank=True, help_text="BA Pick Remarks")  # New field
    IQF_pick_remarks= models.CharField(max_length=100, null=True, blank=True, help_text="IQF Pick Remarks")  # New field
    
    rejected_tray_scan_status=models.BooleanField(default=False)
    accepted_tray_scan_status=models.BooleanField(default=False)
    ip_onhold_picking =models.BooleanField(default=False)
    
    #Brass QC Module accept and rejection
    brass_qc_accptance=models.BooleanField(default=False)
    brass_qc_few_cases_accptance=models.BooleanField(default=False)
    brass_qc_rejection=models.BooleanField(default=False)
    brass_rejection_tray_scan_status=models.BooleanField(default=False)
    brass_accepted_tray_scan_status=models.BooleanField(default=False)
    brass_onhold_picking=models.BooleanField(default=False, help_text="Brass QC On Hold Picking")
    brass_draft=models.BooleanField(default=False, help_text="Brass QC Draft Save")
    brass_qc_accepted_qty_verified= models.BooleanField(default=False, help_text="Brass QC Accepted Quantity Verified")  # New field

    #Brass Audit Module accept and rejection
    brass_audit_accptance=models.BooleanField(default=False)
    brass_audit_few_cases_accptance=models.BooleanField(default=False)
    brass_audit_rejection=models.BooleanField(default=False)
    brass_audit_rejection_tray_scan_status=models.BooleanField(default=False)
    brass_audit_accepted_tray_scan_status=models.BooleanField(default=False)
    brass_audit_onhold_picking=models.BooleanField(default=False, help_text="Brass Audit On Hold Picking")
    brass_audit_accepted_qty_verified= models.BooleanField(default=False, help_text="Brass QC Accepted Quantity Verified")  # New field
    brass_audit_accepted_qty = models.IntegerField(default=0, help_text="Brass audit Accepted Quantity")  # New field
    brass_audit_draft=models.BooleanField(default=False, help_text="Brass Audit Draft Save")

    #IQF Module accept and rejection
    iqf_accepted_qty_verified=models.BooleanField(default=False, help_text="IQF Accepted Quantity Verified")  # New field
    iqf_acceptance=models.BooleanField(default=False)
    iqf_few_cases_acceptance=models.BooleanField(default=False)
    iqf_rejection=models.BooleanField(default=False)
    iqf_rejection_tray_scan_status=models.BooleanField(default=False)
    iqf_accepted_tray_scan_status=models.BooleanField(default=False)
    iqf_onhold_picking=models.BooleanField(default=False, help_text="IQF On Hold Picking")
    tray_verify=models.BooleanField(default=False, help_text="Tray Verify")
    #Module is IQF - Acceptance - Send to Brass QC 
    send_brass_qc=models.BooleanField(default=False, help_text="Send to Brass QC")
    send_brass_audit_to_qc=models.BooleanField(default=False, help_text="Send to Brass Audit QC")
    send_brass_audit_to_iqf=models.BooleanField(default=False, help_text="Send to IQF")

    # ═══ Transition Lot ID Tracking ═══
    brass_qc_transition_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition lot_id from Brass QC (FULL_ACCEPT/FULL_REJECT)")
    brass_qc_transition_accept_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition accept lot_id from Brass QC (PARTIAL)")
    brass_qc_transition_reject_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition reject lot_id from Brass QC (PARTIAL)")
    brass_qc_transition_label = models.CharField(max_length=200, null=True, blank=True, help_text="Brass QC transition label")
    brass_audit_transition_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition lot_id from Brass Audit (FULL_ACCEPT/FULL_REJECT)")
    brass_audit_transition_accept_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition accept lot_id from Brass Audit (PARTIAL)")
    brass_audit_transition_reject_lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Transition reject lot_id from Brass Audit (PARTIAL)")
    brass_audit_transition_label = models.CharField(max_length=200, null=True, blank=True, help_text="Brass Audit transition label")
    
    jig_lot_status = models.CharField(
        max_length=50,
        choices=[
            ('READY', 'Ready for Jig Loading'),
            ('PARTIAL_DRAFT', 'Partial Draft - Model 2+ in Progress'),
            ('FULL_DRAFT', 'Full Draft - Awaiting Submit'),
            ('SUBMITTED', 'Submitted to IP Inspection'),
        ],
        default='READY',
        help_text='Jig Loading lot status - controls Add Mode eligibility',
    )
    jig_draft=models.BooleanField(default=False, help_text="Jig Draft Save")
    Jig_Load_completed =models.BooleanField(default=False, help_text="Jig Load Completed")
    jig_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Reason for holding the batch")
    jig_release_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Reason for releasing the batch")
    jig_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Jig")
    jig_release_lot =models.BooleanField(default=False)
    jig_hold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='jig_hold_events', help_text="User who held this lot in Jig Loading")
    jig_hold_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was held in Jig Loading")
    jig_release_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='jig_release_events', help_text="User who released this lot in Jig Loading")
    jig_release_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was released in Jig Loading")
    jig_pick_remarks = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Pick Remarks")
    
    inprocess_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Inprocess Reason for holding the batch")
    inprocess_release_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Inprocess Reason for releasing the batch")
    inprocess_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Inprocess")
    inprocess_release_lot = models.BooleanField(default=False)
    
    ip_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="IP Reason for holding the batch")  
    ip_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="IP Reason for releasing the batch")
    ip_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n IP")
    ip_release_lot =models.BooleanField(default=False)
    
    brass_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for holding the batch")  
    brass_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for releasing the batch")
    brass_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Brass")
    brass_release_lot =models.BooleanField(default=False)
    brass_hold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='brass_hold_events', help_text="User who held this lot in Brass QC")
    brass_hold_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was held in Brass QC")
    brass_release_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='brass_release_events', help_text="User who released this lot in Brass QC")
    brass_release_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was released in Brass QC")

    brass_audit_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for holding the batch")
    brass_audit_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for releasing the batch")
    brass_audit_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Brass")
    brass_audit_release_lot =models.BooleanField(default=False)
    brass_audit_hold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='brass_audit_hold_events', help_text="User who held this lot in Brass Audit")
    brass_audit_hold_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was held in Brass Audit")
    brass_audit_release_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='brass_audit_release_events', help_text="User who released this lot in Brass Audit")
    brass_audit_release_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this lot was released in Brass Audit")

    iqf_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="IQF Reason for holding the batch")  
    iqf_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="IQF Reason for releasing the batch")
    iqf_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n IQF")
    iqf_release_lot =models.BooleanField(default=False)
    
    ip_top_tray_qty_verified = models.BooleanField(default=False, help_text="IP-On Hold Picking")
    ip_verified_tray_qty=models.IntegerField(default=0, help_text="IP-Verified Tray Quantity")
    ip_top_tray_qty_modify=models.IntegerField(default=0, help_text="IP-Top Tray Quantity Modified")
    ip_draft_screening = models.BooleanField(default=False, help_text="IS Reject modal draft saved — S circle half-green")

    is_split = models.BooleanField(default=False, help_text="Flag to mark lot as split into accept/reject portions")
    remove_lot=models.BooleanField(default=False, help_text="Indicates if the lot is to be removed")

    # ═══ Centralized Stage Tracking — Single Source of Truth ═══
    # Updated only on actual processing activity: draft save, qty verify, submit, accept, reject.
    # Never updated on view/read operations, search, or navigation.
    current_stage = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Current active stage — updated on actual processing (draft/verify/submit/accept/reject)"
    )

    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.model_stock_no.model_no} - {self.version.version_name} - {self.lot_id}"

    def delete(self, *args, **kwargs):
        if self.lot_id:
            # Delete related records with the same lot_id
            TrayId.objects.filter(lot_id=self.lot_id).delete()
            DraftTrayId.objects.filter(lot_id=self.lot_id).delete()
            DP_TrayIdRescan.objects.filter(lot_id=self.lot_id).delete()
            IP_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            Brass_QC_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            IQF_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            IP_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            Brass_QC_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IQF_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IP_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            Brass_Qc_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IQF_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IP_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
            Brass_Qc_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
            IQF_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
        
        super().delete(*args, **kwargs)



class DP_TrayIdRescan(models.Model):
    """
    Stores tray ID rescans during the day planning process.
    """
    tray_id = models.CharField(max_length=100, unique=True)
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    scan_count = models.PositiveIntegerField(default=1)  # Count how many times scanned

    class Meta:
        unique_together = ('tray_id', 'lot_id')  # Ensure each tray_id and lot_id combination is unique

    def __str__(self):
        return f"{self.tray_id} - {self.lot_id} (Scanned: {self.scan_count})"

     

  
class Nickle_IP_Rejection_Table(models.Model):
    group = models.ForeignKey(IP_RejectionGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='nickle_rejection_reasons')
    rejection_reason_id = models.CharField(max_length=10, null=True, blank=True, editable=False)
    rejection_reason = models.TextField(help_text="Reason for rejection")
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.rejection_reason_id:
            last = Nickle_IP_Rejection_Table.objects.order_by('-rejection_reason_id').first()
            if last and last.rejection_reason_id.startswith('R'):
                last_num = int(last.rejection_reason_id[1:])
                new_num = last_num + 1
            else:
                new_num = 1
            self.rejection_reason_id = f"R{new_num:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rejection_reason}"

#rejection reasons stored tabel , fields ared rejection resoon multiple slection from RejectionTable an dlot_id , user, Total_rejection_qunatity
class Nickle_IP_Rejection_ReasonStore(models.Model):
    rejection_reason = models.ManyToManyField(Nickle_IP_Rejection_Table, blank=True)
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_rejection_quantity = models.PositiveIntegerField(help_text="Total Rejection Quantity")
    batch_rejection=models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user} - {self.total_rejection_quantity} - {self.lot_id}"
    
#give rejected trayscans - fields are lot_id , rejected_tray_quantity , rejected_reson(forign key from RejectionTable), user
class Nickle_IP_Rejected_TrayScan(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    rejected_tray_quantity = models.CharField(help_text="Rejected Tray Quantity")
    rejected_tray_id= models.CharField(max_length=100, null=True, blank=True, help_text="Rejected Tray ID")
    rejection_reason = models.ForeignKey(Nickle_IP_Rejection_Table, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.rejection_reason} - {self.rejected_tray_quantity} - {self.lot_id}"

class Nickle_IP_Accepted_TrayScan(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    accepted_tray_quantity = models.CharField(help_text="Accepted Tray Quantity")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.accepted_tray_quantity} - {self.lot_id}"
    
class Nickle_IP_Accepted_TrayID_Store(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, unique=True)
    tray_qty = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_draft = models.BooleanField(default=False, help_text="Draft Save")
    is_save= models.BooleanField(default=False, help_text="Save")
     
    def __str__(self):
        return f"{self.tray_id} - {self.lot_id}"
    
class Nickle_Audit_Rejection_Table(models.Model):
    group = models.ForeignKey(IP_RejectionGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='nickle_audit_rejection_reasons')
    rejection_reason_id = models.CharField(max_length=10, null=True, blank=True, editable=False)
    rejection_reason = models.TextField(help_text="Reason for rejection")
    createdby= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.rejection_reason_id:
            last = Nickle_Audit_Rejection_Table.objects.order_by('-rejection_reason_id').first()
            if last and last.rejection_reason_id.startswith('R'):
                last_num = int(last.rejection_reason_id[1:])
                new_num = last_num + 1
            else:
                new_num = 1
            self.rejection_reason_id = f"R{new_num:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rejection_reason}"

#rejection reasons stored tabel , fields ared rejection resoon multiple slection from RejectionTable an dlot_id , user, Total_rejection_qunatity
class Nickle_Audit_Rejection_ReasonStore(models.Model):
    rejection_reason = models.ManyToManyField(Nickle_Audit_Rejection_Table, blank=True)
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_rejection_quantity = models.PositiveIntegerField(help_text="Total Rejection Quantity")
    batch_rejection=models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user} - {self.total_rejection_quantity} - {self.lot_id}"
    
#give rejected trayscans - fields are lot_id , rejected_tray_quantity , rejected_reson(forign key from RejectionTable), user
class Nickle_Audit_Rejected_TrayScan(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    rejected_tray_quantity = models.CharField(help_text="Rejected Tray Quantity")
    rejected_tray_id= models.CharField(max_length=100, null=True, blank=True, help_text="Rejected Tray ID")
    rejection_reason = models.ForeignKey(Nickle_Audit_Rejection_Table, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.rejection_reason} - {self.rejected_tray_quantity} - {self.lot_id}"

class Nickle_Audit_Accepted_TrayScan(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    accepted_tray_quantity = models.CharField(help_text="Accepted Tray Quantity")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.accepted_tray_quantity} - {self.lot_id}"
    
class Nickle_Audit_Accepted_TrayID_Store(models.Model):
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, unique=True)
    tray_qty = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_draft = models.BooleanField(default=False, help_text="Draft Save")
    is_save= models.BooleanField(default=False, help_text="Save")
     
    def __str__(self):
        return f"{self.tray_id} - {self.lot_id}"
    
    
    
class TrayAutoSaveData(models.Model):
    """
    Model to store auto-save data for tray scan modal
    Supports cross-browser and user-specific auto-save
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tray_autosave')
    batch_id = models.CharField(max_length=100, db_index=True)
    auto_save_data = models.JSONField()  # Stores the complete tray data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'batch_id']  # One auto-save per user per batch
        db_table = 'tray_auto_save_data'
        indexes = [
            models.Index(fields=['user', 'batch_id']),
            models.Index(fields=['updated_at']),
        ]
    
    def is_expired(self, hours=24):
        """Check if auto-save data is older than specified hours"""
        from datetime import timedelta
        return timezone.now() - self.updated_at > timedelta(hours=hours)
    
    def __str__(self):
        return f"AutoSave: {self.user.username} - {self.batch_id}"
    


from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=ModelMasterCreation)
def delete_related_trayids(sender, instance, **kwargs):
    TrayId.objects.filter(batch_id=instance).delete()
    DraftTrayId.objects.filter(batch_id=instance).delete()


# ═══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL LOT MASTER — STRICT HIERARCHY LOT SNAPSHOT ARCHITECTURE
# Every partial/full submission creates a new LotMaster row.
# Parent lot becomes history. Child lot becomes the active SSOT.
# ═══════════════════════════════════════════════════════════════════════════════

class LotMaster(models.Model):
    """
    Universal lot tracking table across all manufacturing modules.

    Rules:
    - Every submit (full accept / full reject / partial) creates one new row.
    - parent_lot_id points to the immediate predecessor lot.
    - root_lot_id always points to the original Day Planning lot.
    - Only one lot per root lineage can have active=True in a given module.
    - Downstream modules must ONLY read trays of the active=True lot.
    """

    MODULE_CHOICES = [
        ('INPUT_SCREENING', 'Input Screening'),
        ('BRASS_QC',        'Brass QC'),
        ('BRASS_AUDIT',     'Brass Audit'),
        ('IQF',             'IQF'),
        ('JIG_LOADING',     'Jig Loading'),
        ('DAY_PLANNING',    'Day Planning'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE',    'Active'),
        ('HISTORY',   'History'),
        ('REJECTED',  'Rejected'),
        ('COMPLETED', 'Completed'),
    ]

    SUBMISSION_TYPE_CHOICES = [
        ('FULL_ACCEPT',    'Full Accept'),
        ('PARTIAL_ACCEPT', 'Partial Accept'),
        ('FULL_REJECT',    'Full Reject'),
        ('PARTIAL_REJECT', 'Partial Reject'),
        ('DRAFT',          'Draft'),
        ('ORIGIN',         'Origin'),
    ]

    # ── Identifiers ────────────────────────────────────────────────────────────
    lot_id        = models.CharField(max_length=50, unique=True, db_index=True,
                                     help_text="LID-format lot ID — generated by generate_lot_id()")
    parent_lot_id = models.CharField(max_length=50, null=True, blank=True, db_index=True,
                                     help_text="Immediate parent lot_id (None for root/origin lots)")
    root_lot_id   = models.CharField(max_length=50, null=True, blank=True, db_index=True,
                                     help_text="Original root lot_id before any splits (Day Planning origin)")

    # ── Batch linkage ──────────────────────────────────────────────────────────
    batch_id = models.ForeignKey(
        'ModelMasterCreation',
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Batch this lot belongs to"
    )

    # ── Module tracking ────────────────────────────────────────────────────────
    module_name   = models.CharField(max_length=50, choices=MODULE_CHOICES,
                                     help_text="Module that currently owns / processes this lot")
    source_module = models.CharField(max_length=50, choices=MODULE_CHOICES, null=True, blank=True,
                                     help_text="Module that generated / sent this lot")

    # ── State ──────────────────────────────────────────────────────────────────
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE',
                                  db_index=True)
    active     = models.BooleanField(default=True, db_index=True,
                                     help_text="True = current SSOT for this lineage; False = history only")
    total_qty  = models.IntegerField(default=0,
                                     help_text="Accepted/forwarded qty at the moment this lot was created")
    rejected_qty = models.IntegerField(default=0,
                                       help_text="Rejected qty at the moment this lot was created")

    # ── Submission context ─────────────────────────────────────────────────────
    submission_type = models.CharField(
        max_length=20,
        choices=SUBMISSION_TYPE_CHOICES,
        null=True, blank=True,
        help_text="Type of submission that created this lot"
    )

    # ── Audit ──────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='lotmaster_created')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks    = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name        = 'Lot Master'
        verbose_name_plural = 'Lot Masters'
        ordering            = ['-created_at']
        indexes = [
            models.Index(fields=['lot_id']),
            models.Index(fields=['parent_lot_id']),
            models.Index(fields=['root_lot_id']),
            models.Index(fields=['active', 'module_name']),
            models.Index(fields=['batch_id', 'active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        parent = f" ← {self.parent_lot_id}" if self.parent_lot_id else " [ROOT]"
        return f"[{self.module_name}] {self.lot_id}{parent} | qty={self.total_qty} | {self.status}"


class LotTraySnapshot(models.Model):
    """
    Frozen tray snapshot attached to a LotMaster row.

    Created once at submit time. Never modified afterwards.
    Downstream modules read ONLY these rows — never raw scan tables.

    tray_order must be preserved exactly as stored. Never auto-sorted.
    """

    TRAY_STATUS_CHOICES = [
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('DELINKED', 'Delinked'),
        ('PARTIAL',  'Partial'),
    ]

    lot         = models.ForeignKey(
        LotMaster,
        on_delete=models.CASCADE,
        related_name='tray_snapshots',
        help_text="Parent LotMaster this snapshot belongs to"
    )
    tray_id     = models.CharField(max_length=100, db_index=True)
    tray_qty    = models.IntegerField(help_text="Qty in this tray at time of snapshot")
    tray_order  = models.PositiveIntegerField(
        help_text="Insertion order at submission time — use this for display; never re-sort by tray_id"
    )
    top_tray    = models.BooleanField(default=False)
    tray_status = models.CharField(max_length=20, choices=TRAY_STATUS_CHOICES, default='ACCEPTED')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Lot Tray Snapshot'
        verbose_name_plural = 'Lot Tray Snapshots'
        ordering            = ['tray_order']
        indexes = [
            models.Index(fields=['lot', 'tray_order']),
            models.Index(fields=['tray_id']),
            models.Index(fields=['lot', 'tray_status']),
        ]

    def __str__(self):
        top = " [TOP]" if self.top_tray else ""
        return (f"Snapshot: {self.tray_id}{top} qty={self.tray_qty} "
                f"order={self.tray_order} [{self.tray_status}]"
                f" → {self.lot.lot_id}")


class SSOAccount(models.Model):
    """
    Stores the mapping between a Django user and a social/SSO identity.
    Used by watchcase_tracker.sso_pipeline to link Microsoft Entra ID logins
    to existing local accounts.
    """
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sso_accounts')
    provider       = models.CharField(max_length=100, help_text='SSO provider name, e.g. "azuread-oauth2"')
    uid            = models.CharField(max_length=255, help_text='Unique ID from the provider')
    email          = models.EmailField(blank=True, default='')
    name           = models.CharField(max_length=255, blank=True, default='')
    email_verified = models.BooleanField(default=False)
    extra_data     = models.JSONField(default=dict, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('provider', 'uid')
        indexes = [
            models.Index(fields=['provider', 'uid']),
            models.Index(fields=['user']),
        ]
        verbose_name = 'SSO Account'
        verbose_name_plural = 'SSO Accounts'

    def __str__(self):
        return f"{self.provider}:{self.uid} → {self.user.username}"
