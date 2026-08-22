import os
import django

# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from modelmasterapp.models import *
from Jig_Loading.models import *
from Brass_QC.models import *
from BrassAudit.models import *
from InputScreening.models import *
from IQF.models import *
from Jig_Unloading.models import *   # ✅ ADDED
from Nickel_Audit.models import *    # ✅ ADDED
from Nickel_Inspection.models import *
from SpiderSpindle_Z1.models import *
from SpiderSpindle_Z2.models import *

from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import datetime


def clear_database():
    """
    Deletes all records from the specified models.
    """

    # -------------------------------
    # CORE MODELS
    # -------------------------------
    TotalStockModel.objects.all().delete()
    ModelMasterCreation.objects.all().delete()
    TrayAutoSaveData.objects.all().delete()
    Jig.objects.all().delete()
    JigLoadingManualDraft.objects.all().delete()
    JigCompleted.objects.all().delete()
    JigAutoSave.objects.all().delete()

    # -------------------------------
    # BRASS QC
    # -------------------------------
    Brass_QC_Draft_Store.objects.all().delete()
    TrayId.objects.all().delete()
    Brass_TopTray_Draft_Store.objects.all().delete()
    Brass_QC_Rejected_TrayScan.objects.all().delete()
    Brass_QC_Rejection_ReasonStore.objects.all().delete()
    Brass_QC_RawSubmission.objects.all().delete()
    # ⚠️ DO NOT DELETE THIS — master rejection reasons table (same as IQF_Rejection_Table)
    # Brass_QC_Rejection_Table.objects.all().delete()
    Brass_QC_Submission.objects.all().delete()
    Brass_Qc_Accepted_TrayID_Store.objects.all().delete()
    BrassQC_PartialAcceptLot.objects.all().delete()
    BrassQC_PartialRejectLot.objects.all().delete()
    
    

    # -------------------------------
    # BRASS AUDIT
    # -------------------------------
    BrassAuditTrayId.objects.all().delete()
    Brass_Audit_Accepted_TrayID_Store.objects.all().delete()
    Brass_Audit_Rejection_ReasonStore.objects.all().delete()
    Brass_Audit_Draft_Store.objects.all().delete()
    Brass_Audit_TopTray_Draft_Store.objects.all().delete()
    Brass_Audit_Rejected_TrayScan.objects.all().delete()
    Brass_Audit_Accepted_TrayScan.objects.all().delete()
    Brass_Audit_RawSubmission.objects.all().delete()
    Brass_Audit_Submission.objects.all().delete()
    BrassAudit_PartialAcceptLot.objects.all().delete()
    BrassAudit_PartialRejectLot.objects.all().delete()

    # -------------------------------
    # INPUT SCREENING
    # -------------------------------
    IP_Accepted_TrayID_Store.objects.all().delete()
    IP_Rejected_TrayScan.objects.all().delete()
    IP_Rejection_ReasonStore.objects.all().delete()
    IP_Rejection_Draft.objects.all().delete()
    IS_AllocationTray.objects.all().delete()
    IS_PartialAcceptLot.objects.all().delete()
    IS_PartialRejectLot.objects.all().delete()
    InputScreening_Submitted.objects.all().delete()

    # -------------------------------
    # IQF
    # -------------------------------
    IQF_Accepted_TrayID_Store.objects.all().delete()
    IQF_Accepted_TrayScan.objects.all().delete()
    IQF_Draft_Store.objects.all().delete()
    IQF_Rejected_TrayScan.objects.all().delete()
    IQF_Rejection_ReasonStore.objects.all().delete()
    IQFTrayId.objects.all().delete()
    IQF_Submitted.objects.all().delete()

    # ⚠️ DO NOT DELETE THIS
    # IQF_Rejection_Table.objects.all().delete()

    try:
        IQF_OptimalDistribution_Draft.objects.all().delete()
    except NameError:
        pass

    # -------------------------------
    # ✅ JIG UNLOADING (NEWLY ADDED)
    # Covers:
    # /jigunloadaftertable/
    # /jigunloadautosave/
    # /jigunloaddraft/
    # /jigunload_trayid/
    # /jusubmittedz1/
    # -------------------------------
    try:
        JigUnloadAfterTable.objects.all().delete()
        JigUnloadAutoSave.objects.all().delete()
        JigUnloadDraft.objects.all().delete()
        JigUnload_TrayId.objects.all().delete()
        JUSubmittedZ1.objects.all().delete()
    except NameError:
        print("⚠️ Some Jig_Unloading models not found")

    # -------------------------------
    # ✅ NICKEL AUDIT
    # /nickel_audittrayid/
    # /nickel_audit_accepted_trayid_store/
    # /nickel_audit_rejection_reasonstore/
    # -------------------------------
    try:
        Nickel_AuditTrayId.objects.all().delete()
        Nickel_Audit_Accepted_TrayID_Store.objects.all().delete()
        Nickel_Audit_Rejection_ReasonStore.objects.all().delete()
    except NameError:
        print("⚠️ Some Nickel_Audit models not found")

    # -------------------------------
    # ✅ NICKEL INSPECTION
    # /nickelqctrayid/
    # /nickel_qc_accepted_trayid_store/
    # /nickel_qc_rejected_trayscan/
    # /nickel_qc_rejection_reasonstore/
    # /nickelwiping_fullacceptrecord/
    # /nickelwiping_fullrejectrecord/
    # /nickelwiping_partialacceptrecord/
    # /nickelwiping_partialrejectrecord/
    # -------------------------------
    try:
        NickelQcTrayId.objects.all().delete()
        Nickel_Qc_Accepted_TrayID_Store.objects.all().delete()
        Nickel_QC_Rejected_TrayScan.objects.all().delete()
        Nickel_QC_Rejection_ReasonStore.objects.all().delete()
        NickelWiping_FullAcceptRecord.objects.all().delete()
        NickelWiping_FullRejectRecord.objects.all().delete()
        NickelWiping_PartialAcceptRecord.objects.all().delete()
        NickelWiping_PartialRejectRecord.objects.all().delete()
    except NameError:
        print("⚠️ Some Nickel_Inspection models not found")

    # -------------------------------
    # ✅ SPIDER SPINDLE
    # /spiderspindlez1trayid/
    # /spiderspindlez2trayid/
    # -------------------------------
    try:
        SpiderSpindleZ1TrayId.objects.all().delete()
        SpiderSpindleZ2TrayId.objects.all().delete()
    except NameError:
        print("⚠️ Some SpiderSpindle models not found")

    print("✅ All specified model data deleted successfully.")

def load_trays():
    """
    Create trays for prefixes NR, JR, ND, JD, NL, JL, NB, JB (default 500 each).
    """

    prefixes = ['NR', 'JR', 'ND', 'JD', 'NL', 'JL', 'NB', 'JB']
    per_prefix = 3000

    normal_tt = TrayType.objects.filter(tray_type__iexact='Normal').first()
    jumbo_tt = TrayType.objects.filter(tray_type__iexact='Jumbo').first()

    normal_cap = int(getattr(normal_tt, 'tray_capacity', 16) or 16)
    jumbo_cap = int(getattr(jumbo_tt, 'tray_capacity', 12) or 12)

    normal_label = normal_tt.tray_type if normal_tt else 'Normal'
    jumbo_label = jumbo_tt.tray_type if jumbo_tt else 'Jumbo'

    admin_user = get_user_model().objects.filter(is_superuser=True).first()

    total_created = 0

    with transaction.atomic():
        for p in prefixes:
            cap = normal_cap if p.startswith('N') else jumbo_cap
            label = normal_label if p.startswith('N') else jumbo_label

            to_create = []

            for i in range(1, per_prefix + 1):
                tid = f"{p}-A{i:05d}"

                if TrayId.objects.filter(tray_id=tid).exists():
                    continue

                to_create.append(TrayId(
                    tray_id=tid,
                    tray_type=label,
                    tray_capacity=cap,
                    new_tray=True,
                    scanned=False,
                    user=admin_user,
                ))

            if to_create:
                TrayId.objects.bulk_create(to_create, batch_size=500)

            created = len(to_create)
            print(f'{p}: created {created}')
            total_created += created

    print(f'TOTAL CREATED: {total_created}')


if __name__ == "__main__":
    clear_database()
    load_trays()

    # -------------------------------
    # RUN ADDITIONAL SCRIPTS
    # -------------------------------
    import subprocess
    import sys

    python_exe = sys.executable

    scripts_to_run = [
        "Jig_Loading.Jig_Id",
    ]

    for module in scripts_to_run:
        print(f"Running module {module}...")
        try:
            subprocess.run([python_exe, "-m", module], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running {module}: {e}")

    print("✅ All scripts executed successfully.")