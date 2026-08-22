# Update the script to set forging_info to 'Bright' for the specified stock numbers, and add the new stock number

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from modelmasterapp.models import ModelMaster
from Jig_Loading.models import JigLoadingMaster

# List of tuples: (Plating Stock No, Jig Type, Jig Capacity)
DATA = [
    ("2617SAA02", "Cylindrical", 144),
    ("2617WAA02", "Cylindrical", 144),
    ("2617SAB02", "Cylindrical", 144),
    ("2617WAB02", "Cylindrical", 144),
    ("2617WAC02", "Cylindrical", 144),
    ("2617YAC02/2N", "Cylindrical", 144),
    ("2617NAD02", "Cylindrical", 144),
    ("2617SAD02", "Cylindrical", 144),
    ("2617YAD02/2N", "Cylindrical", 144),
    ("2617NSA02", "Cylindrical", 144),
    ("2648NAA02", "Cylindrical", 144),
    ("2648QAA02/BRN", "Cylindrical", 144),
    ("2648SAA02", "Cylindrical", 144),
    ("2648WAA02", "Cylindrical", 144),
    ("2648YAA02/2N", "Cylindrical", 144),
    ("2648KAB02/RGSS", "Cylindrical", 144),
    ("2648QAB02/GUN", "Cylindrical", 144),
    ("2648SAB02", "Cylindrical", 144),
    ("2648WAB02", "Cylindrical", 144),
    ("2648QAD02/BRN", "Cylindrical", 144),
    ("2648SAD02", "Cylindrical", 144),
    ("2648WAD02", "Cylindrical", 144),
    ("2648SAE02", "Cylindrical", 144),
    ("2648WAE02", "Cylindrical", 144),
    ("2648QAF02/BRN", "Cylindrical", 144),
    ("2648SAF02", "Cylindrical", 144),
    ("2648WAF02", "Cylindrical", 144),
    ("2648QAE02/BRN", "Cylindrical", 144),
    ("1805NAA02", "Cylindrical", 98),
    ("1805SAA02", "Cylindrical", 98),
    ("1805WAA02", "Cylindrical", 98),
    ("1805NAD02", "Cylindrical", 98),
    ("1805QAD02/GUN", "Cylindrical", 98),
    ("1805SAD02", "Cylindrical", 98),
    ("1805NAK02", "Cylindrical", 98),
    ("1805SAK02", "Cylindrical", 98),
    ("1805WAK02", "Cylindrical", 98),
    ("1805YAK02/2N", "Cylindrical", 98),
    ("1805NAR02", "Cylindrical", 98),
    ("1805QBK02/GUN", "Cylindrical", 98),
    ("1805WBK02", "Cylindrical", 98),
    ("1805QCL02/GUN", "Cylindrical", 98),
    ("1805QSP02/GUN", "Cylindrical", 98),
    ("1805BAA02", "Cylindrical", 98),  # Added missing stock number
    ("B1805SAA02", "Cylindrical", 98),  # Added new stock number
]

# Set of stock numbers that should have 'Bright' nickel bath type
bright_stock_nos = {
    "2617SAA02", "2617WAA02", "2617SAB02", "2617WAB02", "2617WAC02", "2617YAC02/2N",
    "2617NAD02", "2617SAD02", "2617YAD02/2N", "2648NAA02", "2648QAA02/BRN",
    "2648SAA02", "2648WAA02", "2648YAA02/2N", "2648KAB02/RGSS", "2648QAB02/GUN",
    "2648SAB02", "2648WAB02", "2648QAD02/BRN", "2648SAD02", "2648WAD02",
    "2648SAE02", "2648WAE02", "2648QAF02/BRN", "2648SAF02", "2648WAF02",
    "2648QAE02/BRN", "1805NAA02", "1805SAA02", "1805WAA02", "1805NAD02",
    "1805QAD02/GUN", "1805SAD02", "1805NAK02", "1805SAK02", "1805WAK02",
    "1805YAK02/2N", "1805NAR02", "B1805SAA02", "1805BAA02"
}

def add_all_jig_loading_masters():
    for stock_no, jig_type, jig_capacity in DATA:
        try:
            model = ModelMaster.objects.get(plating_stk_no=stock_no)
            nickel_bath = 'Bright' if stock_no in bright_stock_nos else ''
            obj, created = JigLoadingMaster.objects.get_or_create(
                model_stock_no=model,
                defaults={
                    'jig_type': jig_type,
                    'jig_capacity': jig_capacity,
                    'forging_info': nickel_bath
                }
            )
            if created:
                print(f"✅ Added: {stock_no} ({jig_type}, {jig_capacity}, {nickel_bath})")
            else:
                # Update existing entry if forging_info differs
                if obj.forging_info != nickel_bath:
                    obj.forging_info = nickel_bath
                    obj.save()
                    print(f"🔄 Updated: {stock_no} forging_info to {nickel_bath}")
                else:
                    print(f"⚠️ Already exists: {stock_no}")
        except ModelMaster.DoesNotExist:
            print(f"❌ ModelMaster not found: {stock_no}")

if __name__ == "__main__":
    add_all_jig_loading_masters()