import os
import sys
import django

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from Jig_Loading.models import Jig

VARIANTS = [
    "J070", "J098", "J144", "J150", "J180", "J220", "J312"
]

def main():
    created = 0
    for variant in VARIANTS:
        for i in range(1, 51):
            jig_id = f"{variant}-{i:04d}"
            obj, is_created = Jig.objects.get_or_create(jig_qr_id=jig_id)
            if is_created:
                created += 1
                print(f"Created: {jig_id}")
            else:
                print(f"Exists: {jig_id}")
    print(f"Done. Total created: {created}")

if __name__ == "__main__":
    main()