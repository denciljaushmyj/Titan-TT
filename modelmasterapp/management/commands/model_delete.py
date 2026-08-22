from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.management import CommandError

# Import your models here - update the import path based on your app structure
from modelmasterapp.models import (
    ModelMasterCreation, TrayId, DraftTrayId, TotalStockModel,
    DP_TrayIdRescan, Brass_QC_Rejection_ReasonStore,
    IQF_Rejection_ReasonStore, Brass_QC_Rejected_TrayScan, IQF_Rejected_TrayScan, Brass_Qc_Accepted_TrayScan, IQF_Accepted_TrayScan,
     Brass_Qc_Accepted_TrayID_Store, IQF_Accepted_TrayID_Store,TrayAutoSaveData
)
from IQF.models import *
from Jig_Loading.models import JigLoadTrayId,JigDetails
from Jig_Unloading.models import JigUnload_TrayId, JigUnloadAfterTable
from BrassAudit.models import *
from InputScreening.models import (
    IPTrayId, IP_TrayVerificationStatus, IP_Rejection_ReasonStore,
    IP_Rejected_TrayScan, IP_Accepted_TrayScan, IP_Accepted_TrayID_Store, IP_Rejection_Draft,IP_Rejection_Table
)
from Brass_QC.models import *
from Nickel_Audit.models import *
from Nickel_Inspection.models import *
from Recovery_DP.models import *
from Recovery_IS.models import *
from Recovery_Brass_QC.models import *
from Recovery_BrassAudit.models import *
from Recovery_IQF.models import *


class Command(BaseCommand):
    help = 'Delete all data from specified tables'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )
    
    def handle(self, *args, **options):
        # List all model classes you want to clear
        model_list = [
            ModelMasterCreation,
            TrayId,
            IPTrayId,
            BrassTrayId,
            IQFTrayId,
            IP_TrayVerificationStatus,
            DraftTrayId,
            TotalStockModel,
            DP_TrayIdRescan,
            IP_Rejection_Draft,
            IP_Rejection_ReasonStore,
            Brass_QC_Rejection_ReasonStore,
            IQF_Rejection_ReasonStore,
            IP_Rejected_TrayScan,
            Brass_QC_Rejected_TrayScan,
            IQF_Rejected_TrayScan,
            IP_Accepted_TrayScan,
            Brass_Qc_Accepted_TrayScan,
            Brass_Qc_Accepted_TrayID_Store,
            IQF_Accepted_TrayScan,
            IP_Accepted_TrayID_Store,
            Brass_Qc_Accepted_TrayID_Store,
            Brass_QC_Draft_Store,
            Brass_TopTray_Draft_Store,
            Brass_Audit_Rejection_ReasonStore,
            Brass_Audit_Draft_Store,
            Brass_Audit_TopTray_Draft_Store,
            Brass_Audit_Rejected_TrayScan,
            Brass_Audit_Accepted_TrayScan,
            Brass_Audit_Accepted_TrayID_Store,
            IQF_Accepted_TrayID_Store,
            JigDetails,
            JigLoadTrayId,
            JigUnload_TrayId,
            JigUnloadAfterTable,
            TrayAutoSaveData,
            Nickel_AuditTrayId,
            Nickel_Audit_Rejection_ReasonStore,
            Nickel_Audit_Draft_Store,
            Nickel_Audit_TopTray_Draft_Store,
            Nickel_Audit_Rejected_TrayScan,
            Nickel_Audit_Accepted_TrayScan,
            Nickel_Audit_Accepted_TrayID_Store,
            NickelQcTrayId,
            Nickel_QC_Rejection_ReasonStore,
            Nickel_QC_Draft_Store,
            Nickel_QC_TopTray_Draft_Store,
            Nickel_QC_Rejected_TrayScan,
            Nickel_Qc_Accepted_TrayScan,
            Nickel_Qc_Accepted_TrayID_Store,
            RecoveryTrayId,
            RecoveryDraftTrayId,
            RecoveryStockModel,
            RecoveryTrayId_History,
            RecoveryMasterCreation,
            RecoveryIPTrayId,
            RecoveryIP_Rejection_ReasonStore,
            RecoveryIP_Rejected_TrayScan,
            RecoveryIP_Accepted_TrayScan,
            RecoveryIP_Accepted_TrayID_Store,
            RecoveryIP_Rejection_Draft,
            RecoveryBrassTrayId,
            RecoveryBrass_QC_Rejection_ReasonStore,
            RecoveryBrass_QC_Rejected_TrayScan,
            RecoveryBrass_Qc_Accepted_TrayScan,
            RecoveryBrass_Qc_Accepted_TrayID_Store,
            RecoveryBrass_QC_Draft_Store,
            RecoveryBrass_TopTray_Draft_Store,
            RecoveryBrassAuditTrayId,
            RecoveryBrass_Audit_Rejection_ReasonStore,
            RecoveryBrass_Audit_Draft_Store,
            RecoveryBrass_Audit_TopTray_Draft_Store,
            RecoveryBrass_Audit_Rejected_TrayScan,
            RecoveryBrass_Audit_Accepted_TrayScan,
            RecoveryBrass_Audit_Accepted_TrayID_Store,
            RecoveryIQFTrayId,
            RecoveryIQF_Draft_Store,
            RecoveryIQF_Accepted_TrayScan,
            RecoveryIQF_Accepted_TrayID_Store,
            RecoveryIQF_Rejection_ReasonStore,
            RecoveryIQF_Rejected_TrayScan,
            RecoveryIQF_OptimalDistribution_Draft,
        ]
        
        # Show confirmation unless --confirm is used
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    f'This will delete ALL data from {len(model_list)} tables.\n'
                    'This action cannot be undone!'
                )
            )
            
            confirm = input('Type "yes" to continue: ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.SUCCESS('Operation cancelled.'))
                return
        
        # Delete data from all models
        try:
            with transaction.atomic():
                deleted_counts = {}
                total_deleted = 0
                
                for model in model_list:
                    count = model.objects.count()
                    if count > 0:
                        model.objects.all().delete()
                        deleted_counts[model.__name__] = count
                        total_deleted += count
                        self.stdout.write(
                            f'Deleted {count} records from {model.__name__}'
                        )
                
                if total_deleted > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\nSuccessfully deleted {total_deleted} total records '
                            f'from {len(deleted_counts)} tables.'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING('No records found to delete.')
                    )
                    
        except Exception as e:
            raise CommandError(f'Error occurred while deleting data: {str(e)}')