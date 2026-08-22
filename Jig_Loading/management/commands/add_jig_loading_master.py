from django.core.management.base import BaseCommand
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

    ("B1805SAA02", "Cylindrical", 98),  # NEW STOCK NUMBER
]


# Stock numbers which should have forging_info = "Bright"
BRIGHT_STOCK_NOS = {
    "2617SAA02", "2617WAA02", "2617SAB02", "2617WAB02",
    "2617WAC02", "2617YAC02/2N", "2617NAD02", "2617SAD02",
    "2617YAD02/2N",

    "2648NAA02", "2648QAA02/BRN", "2648SAA02", "2648WAA02",
    "2648YAA02/2N", "2648KAB02/RGSS", "2648QAB02/GUN",
    "2648SAB02", "2648WAB02", "2648QAD02/BRN",
    "2648SAD02", "2648WAD02", "2648SAE02", "2648WAE02",
    "2648QAF02/BRN", "2648SAF02", "2648WAF02",
    "2648QAE02/BRN",

    "1805NAA02", "1805SAA02", "1805WAA02", "1805NAD02",
    "1805QAD02/GUN", "1805SAD02", "1805NAK02",
    "1805SAK02", "1805WAK02", "1805YAK02/2N",
    "1805NAR02",

    "B1805SAA02"
}


class Command(BaseCommand):
    help = "Insert / Update JigLoadingMaster and set forging_info as Bright where applicable"

    def handle(self, *args, **options):
        for stock_no, jig_type, jig_capacity in DATA:
            try:
                model = ModelMaster.objects.get(plating_stk_no=stock_no)

                forging_info = "Bright" if stock_no in BRIGHT_STOCK_NOS else ""

                obj, created = JigLoadingMaster.objects.get_or_create(
                    model_stock_no=model,
                    defaults={
                        "jig_type": jig_type,
                        "jig_capacity": jig_capacity,
                        "forging_info": forging_info
                    }
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Added → {stock_no} | {jig_type} | {jig_capacity} | {forging_info}"
                        )
                    )
                else:
                    # jig_capacity/jig_type drive the Jig ID format validation, so an
                    # existing row must be kept in sync with this source list too —
                    # get_or_create's defaults only apply on insert, never on update.
                    changed_fields = []
                    if obj.jig_capacity != jig_capacity:
                        obj.jig_capacity = jig_capacity
                        changed_fields.append(f"jig_capacity={jig_capacity}")
                    if obj.jig_type != jig_type:
                        obj.jig_type = jig_type
                        changed_fields.append(f"jig_type={jig_type}")
                    if obj.forging_info != forging_info:
                        obj.forging_info = forging_info
                        changed_fields.append(f"forging_info={forging_info}")

                    if changed_fields:
                        obj.save()
                        self.stdout.write(
                            self.style.WARNING(
                                f"Updated → {stock_no}: " + ", ".join(changed_fields)
                            )
                        )
                    else:
                        self.stdout.write(f"Already exists → {stock_no}")

            except ModelMaster.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"ModelMaster NOT FOUND → {stock_no}")
                )
