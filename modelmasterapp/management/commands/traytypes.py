from django.core.management.base import BaseCommand
from django.db import transaction
from modelmasterapp.models import TrayType

class Command(BaseCommand):
    help = 'Create TrayType master records with tray codes'

    def handle(self, *args, **options):
        tray_types_data = [
            # Normal trays (16 capacity)
            ('NR', 16, 'Red'),      # IPS colors - Zone 1
            ('ND', 16, 'Dark Green'),  # Other colors - Zone 2
            ('NL', 16, 'Light Green'), # Bi-color
            ('NB', 16, 'Light Green'), # Bi-color alternate
            
            # Jumbo trays (12 capacity)
            ('JR', 12, 'Red'),      # IPS colors - Zone 1
            ('JD', 12, 'Dark Green'),  # Other colors - Zone 2
            ('JL', 12, 'Light Green'), # Bi-color
            ('JB', 12, 'Light Green'), # Bi-color alternate
        ]
        
        with transaction.atomic():
            # Clear existing generic types (optional)
            # TrayType.objects.filter(tray_type__in=['Normal', 'Jumbo']).delete()
            
            created_count = 0
            for tray_code, capacity, color in tray_types_data:
                obj, created = TrayType.objects.get_or_create(
                    tray_type=tray_code,
                    defaults={'tray_capacity': capacity, 'tray_color': color}
                )
                if created:
                    self.stdout.write(f'✅ Created: {tray_code} - Capacity: {capacity}')
                    created_count += 1
                else:
                    self.stdout.write(f'⚠️  Already exists: {tray_code}')
            
            self.stdout.write(self.style.SUCCESS(f'\n🎉 Total created: {created_count} TrayType records'))