from django.db import models
from Recovery_IS.models import *
from modelmasterapp.models import *
from Recovery_DP.models import *

class RecoveryLocation(models.Model):
    location_name = models.CharField(max_length=255, unique=True, help_text="Name of the location")
    date_time = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.location_name
    
class RecoveryMasterCreation(models.Model):
    
    #unique_id = models.CharField(max_length=100, unique=True,null=True, blank=True) #not in use
    batch_id = models.CharField(max_length=50, unique=True)
    lot_id = models.CharField(max_length=100, unique=True, null=True, blank=True)  # <== ADD THIS LINE
    model_stock_no = models.ForeignKey(
        ModelMaster,
        related_name='recovery_master_creations',  # <-- unique related_name
        on_delete=models.CASCADE
    )
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
    location = models.ForeignKey(RecoveryLocation, on_delete=models.SET_NULL, null=True, blank=True)  # Allow null values
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
    changes = models.TextField(blank=True, null=True,default="Outer Groove")
    
    def save(self, *args, **kwargs):
    
        if not self.pk:  # Only set the sequence number for new instances
            last_batch = RecoveryMasterCreation.objects.order_by('-sequence_number').first()
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
    
class RecoveryTrayId(models.Model):
    """
    RecoveryTrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, unique=True, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(RecoveryMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
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
        verbose_name = "Tray ID"
        verbose_name_plural = "Recovery Tray IDs"

class RecoveryDraftTrayId(models.Model):
    """
    RecoveryTrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, blank=True, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(RecoveryMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
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
                name='recovery_unique_non_empty_tray_id_per_batch'
            )
        ]
    
    def __str__(self):
        return f"{self.tray_id or 'Empty'} - Position {self.position} - {self.tray_quantity}"  

class RecoveryStockModel(models.Model):
    """
    This model is for saving overall stock in Day Planning operation form.
  
    """
    batch_id = models.ForeignKey(RecoveryMasterCreation, on_delete=models.CASCADE, null=True, blank=True)

    model_stock_no = models.ForeignKey(ModelMaster, on_delete=models.CASCADE, help_text="Model Stock Number")
    version = models.ForeignKey(Version, on_delete=models.CASCADE, help_text="Version")
    total_stock = models.IntegerField(help_text="Total stock quantity")
    polish_finish = models.ForeignKey(PolishFinishType, on_delete=models.SET_NULL, null=True, blank=True, help_text="Polish Finish")

    plating_color = models.ForeignKey(Plating_Color, on_delete=models.SET_NULL, null=True, blank=True, help_text="Plating Color")
    location = models.ManyToManyField(RecoveryLocation, blank=True, help_text="Multiple Locations")
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
    jig_pick_remarks = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Pick Remarks")
    
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
    
    # New fields for Jig status
    Jig_Load_completed =models.BooleanField(default=False, help_text="Jig Load Completed")
    jig_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Reason for holding the batch")
    jig_release_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Jig Reason for releasing the batch")
    jig_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Jig")
    jig_release_lot =models.BooleanField(default=False)
        
    
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
    
    brass_audit_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for holding the batch")  
    brass_audit_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="Brass Reason for releasing the batch")
    brass_audit_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n Brass")
    brass_audit_release_lot =models.BooleanField(default=False)

    iqf_holding_reason = models.CharField(max_length=255, null=True, blank=True, help_text="IQF Reason for holding the batch")  
    iqf_release_reason= models.CharField(max_length=255, null=True, blank=True, help_text="IQF Reason for releasing the batch")
    iqf_hold_lot = models.BooleanField(default=False, help_text="Indicates if the lot is on hold n IQF")
    iqf_release_lot =models.BooleanField(default=False)
    
    ip_top_tray_qty_verified = models.BooleanField(default=False, help_text="IP-On Hold Picking")
    ip_verified_tray_qty=models.IntegerField(default=0, help_text="IP-Verified Tray Quantity")
    ip_top_tray_qty_modify=models.IntegerField(default=0, help_text="IP-Top Tray Quantity Modified")
    
    
    def __str__(self):
        return f"{self.model_stock_no.model_no} - {self.version.version_name} - {self.lot_id}"

    def delete(self, *args, **kwargs):
        if self.lot_id:
            # Delete related records with the same lot_id
            RecoveryTrayId.objects.filter(lot_id=self.lot_id).delete()
            RecoveryDraftTrayId.objects.filter(lot_id=self.lot_id).delete()
            DP_TrayIdRescan.objects.filter(lot_id=self.lot_id).delete()
            RecoveryIP_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            Brass_QC_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            IQF_Rejection_ReasonStore.objects.filter(lot_id=self.lot_id).delete()
            RecoveryIP_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            Brass_QC_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IQF_Rejected_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            RecoveryIP_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            Brass_Qc_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            IQF_Accepted_TrayScan.objects.filter(lot_id=self.lot_id).delete()
            RecoveryIP_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
            Brass_Qc_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
            IQF_Accepted_TrayID_Store.objects.filter(lot_id=self.lot_id).delete()
            JigDetails.objects.filter(lot_id=self.lot_id).delete()
        
        super().delete(*args, **kwargs)

class RecoveryTrayId_History(models.Model):
    """
    RecoveryTrayId Model
    Represents a tray identifier in the Titan Track and Traceability system.
    """
    lot_id = models.CharField(max_length=50, null=True, blank=True, help_text="Lot ID")
    tray_id = models.CharField(max_length=100, help_text="Tray ID")
    tray_quantity = models.IntegerField(null=True, blank=True, help_text="Quantity in the tray")
    batch_id = models.ForeignKey(RecoveryMasterCreation, on_delete=models.CASCADE, blank=True, null=True)
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
        verbose_name = "Recovery Tray History ID"
        verbose_name_plural = "Recovery Tray History IDs"

class RecoveryTrayIdRescan(models.Model):
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
