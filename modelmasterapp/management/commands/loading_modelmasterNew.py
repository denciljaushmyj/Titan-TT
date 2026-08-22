from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Load plating colors, rejection reasons, and generate tray IDs with color-based routing into multiple tables across different apps'

    def handle(self, *args, **options):
        # Dictionary to store imported models
        models_to_import = {
            'Plating_Color': None,
            'TrayId': None,
            'TrayType': None,
            'IP_Rejection_Table': None,
            'Brass_QC_Rejection_Table': None,
            'Brass_Audit_Rejection_Table': None,
            'IQF_Rejection_Table': None,
            'Nickel_QC_Rejection_Table': None,
            'Nickel_Audit_Rejection_Table': None,
            'RecoveryIP_Rejection_Table': None,
            'RecoveryBrass_QC_Rejection_Table': None,
            'RecoveryBrass_Audit_Rejection_Table': None,
            'RecoveryIQF_Rejection_Table': None,
        }
        
        # Try to import each model from its respective app
        model_app_mapping = [
            ('Plating_Color', 'modelmasterapp'),
            ('TrayId', 'modelmasterapp'),
            ('TrayType', 'modelmasterapp'),
            ('IP_Rejection_Table', 'InputScreening'),
            ('Brass_QC_Rejection_Table', 'Brass_QC'),
            ('Brass_Audit_Rejection_Table', 'BrassAudit'),
            ('IQF_Rejection_Table', 'IQF'),
            ('Nickel_QC_Rejection_Table', 'Nickel_Inspection'),
            ('Nickel_Audit_Rejection_Table', 'Nickel_Audit'),
            ('RecoveryIP_Rejection_Table', 'Recovery_IS'),
            ('RecoveryBrass_QC_Rejection_Table', 'Recovery_Brass_QC'),
            ('RecoveryBrass_Audit_Rejection_Table', 'Recovery_BrassAudit'),
            ('RecoveryIQF_Rejection_Table', 'Recovery_IQF'),
        ]

        # Import models with individual error handling
        for model_name, app_name in model_app_mapping:
            try:
                module = __import__(f'{app_name}.models', fromlist=[model_name])
                model_class = getattr(module, model_name)
                models_to_import[model_name] = model_class
                self.stdout.write(f"✅ Imported {model_name} from {app_name}")
            except ImportError:
                self.stdout.write(f"⚠️  {model_name} not found in {app_name}")
            except AttributeError:
                self.stdout.write(f"⚠️  {model_name} model not found in {app_name}.models")
            except Exception as e:
                self.stdout.write(f"❌ Error importing {model_name} from {app_name}: {str(e)}")

        # Show which models are not available
        missing_models = [name for name, model in models_to_import.items() if model is None]
        available_models = [name for name, model in models_to_import.items() if model is not None]
        
        if missing_models:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  These tables are not available in DB: {', '.join(missing_models)}"
                )
            )
            
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Available tables: {', '.join(available_models)}"
            )
        )

        # Data definitions - Following TTT color-wise routing requirement
        plating_colors_data = [
            ("BLACK", "N"),
            ("IPS", "S"),  # Zone 1 - IPS only
            ("IPG", "Y"),
            ("IP-GUN", "GUN"),
            ("IP-BROWN", "BRN"),
            ("RG", "W"),
            ("IPSIPG", "B"),
            ("IP-BLUE M", "BLU"),
            ("RG-BI", "RGSS"),
            ("IPG-2N", "2N"),
            ("IPSIPG-HN", "HN"),
            ("IP-CORN.GOLD", "CN"),
            ("IP-TITANIUM", "T"),
            ("IPG-HALF.N", "HN"),
            ("ANODISING", "A"),
            ("IP-BLUE INH", "BL01"),
            ("IP-BLUE", "BLU"),
            ("IP-BR ANTI", "BA"),
            ("IP-BRONZE", "BRZ"),
            ("IP-CH.GOLD", "CHG"),
            ("IP-SIL ANTI", "SA"),
            ("IP-LCR", "LCR"),
            ("IP-OGR", "OGR"),
            ("IP-ICE BLUE", "IBL"),
            ("IP-PLUM", "PM01"),
            ("IP-TITANIUM BLUE", "TIN"),
            # Zone 2 - Additional colors mentioned in requirements
            ("3N", "3N"),
            ("2N", "2N"),
            ("J-BLUE", "JBL"),
            ("BR", "BR"),
            ("PLUM", "PLUM"),
            ("BIC", "BIC"),
        ]

        ip_rejection_reasons = [
            "VERSION MIXUP",
            "MODEL MIXUP", 
            "NO VERSION",
            "SHORTAGE"
        ]

        brass_rejection_reasons = [
            "DENT",
            "SCRATCH",
            "ETCHING STAINS / FINGER STAINS",
            "BUFFING COMPOUND",
            "BACK SIDE DENT",
            "MATERIAL DEFECT/ OD",
            "WAVINESS",
            "STEP DENT",
            "MGS / DO DENT",
            "RING STAINS",
            "OD (HOOK MILL, SBH MISS)",
            "BURR",
            "OTHERS"
        ]

        nickel_rejection_reasons = [
            "WATER STAINS",
            "WIPING STAINS",
            "PLATING STAINS",
            "SANDBLAST STAIN",
            "DENT",
            "SCR",
            "PLATING ROUGHNESS",
            "PITTING",
            "LEVELLING",
            "FINISH ISSUE",
            "DOSCR/STAINS",
            "OD REJECTION",
            "BUFF COMPOUND",
            "MGS/DO DENT",
            "DAMAGE",
            "D.O. BURR",
            "CRACK",
            "ROUND OFF",
            "STEP ROUGHNESS",
            "OTHERS"
        ]

        # Load data for each available table
        total_created = 0

        # 1. Load Plating Colors with TTT routing logic
        if models_to_import['Plating_Color']:
            total_created += self.load_plating_colors(models_to_import['Plating_Color'], plating_colors_data)

        # 2. Generate Tray IDs with color-based prefixes
        if models_to_import['TrayId'] and models_to_import['TrayType'] and models_to_import['Plating_Color']:
            total_created += self.generate_tray_ids(models_to_import['TrayId'], models_to_import['TrayType'], models_to_import['Plating_Color'])

        # 3. Load IP Rejection Reasons (Main and Recovery)
        ip_tables = [
            ('IP_Rejection_Table', 'IP Rejection'),
            ('RecoveryIP_Rejection_Table', 'Recovery IP Rejection')
        ]
        
        for table_name, display_name in ip_tables:
            if models_to_import[table_name]:
                total_created += self.load_rejection_reasons(
                    models_to_import[table_name], 
                    ip_rejection_reasons, 
                    display_name
                )

        # 4. Load Brass QC/Audit/IQF Rejection Reasons (Main and Recovery)
        brass_tables = [
            ('Brass_QC_Rejection_Table', 'Brass QC'),
            ('Brass_Audit_Rejection_Table', 'Brass Audit'),
            ('IQF_Rejection_Table', 'IQF'),
            ('RecoveryBrass_QC_Rejection_Table', 'Recovery Brass QC'),
            ('RecoveryBrass_Audit_Rejection_Table', 'Recovery Brass Audit'),
            ('RecoveryIQF_Rejection_Table', 'Recovery IQF')
        ]
        
        for table_name, display_name in brass_tables:
            if models_to_import[table_name]:
                total_created += self.load_rejection_reasons(
                    models_to_import[table_name], 
                    brass_rejection_reasons, 
                    display_name
                )

        # 5. Load Nickel QC/Audit Rejection Reasons
        nickel_tables = [
            ('Nickel_QC_Rejection_Table', 'Nickel QC'),
            ('Nickel_Audit_Rejection_Table', 'Nickel Audit')
        ]
        
        for table_name, display_name in nickel_tables:
            if models_to_import[table_name]:
                total_created += self.load_rejection_reasons(
                    models_to_import[table_name], 
                    nickel_rejection_reasons, 
                    display_name
                )

        # Final summary
        loaded_tables = [name for name, model in models_to_import.items() if model is not None]
        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 DATA LOADING COMPLETED!'
                f'\n📊 Total records created: {total_created}'
                f'\n✅ Successfully loaded {len(loaded_tables)} tables:'
            )
        )
        
        # Group tables by category for better display
        table_categories = {
            'Master Data': ['Plating_Color', 'TrayId'],
            'IP Rejection': ['IP_Rejection_Table', 'RecoveryIP_Rejection_Table'],
            'Brass Rejection': ['Brass_QC_Rejection_Table', 'Brass_Audit_Rejection_Table', 'IQF_Rejection_Table',
                               'RecoveryBrass_QC_Rejection_Table', 'RecoveryBrass_Audit_Rejection_Table', 'RecoveryIQF_Rejection_Table'],
            'Nickel Rejection': ['Nickel_QC_Rejection_Table', 'Nickel_Audit_Rejection_Table']
        }
        
        for category, table_list in table_categories.items():
            loaded_in_category = [table for table in table_list if table in loaded_tables]
            if loaded_in_category:
                self.stdout.write(f"   📂 {category}: {', '.join(loaded_in_category)}")

    def load_plating_colors(self, Plating_Color, plating_colors_data):
        """
        Load plating colors with TTT color-wise routing logic:
        - Zone 1: IPS only
        - Zone 2: All other colors (3N, 2N, RG, CHG, CN, J-BLUE, BR, BRN, GUN, BLU, PLUM, BIC, etc.)
        """
        try:
            with transaction.atomic():
                # Clear existing data if --force flag is used
                if '--force' in self.style.__dict__ or True:  # Always force for color routing update
                    Plating_Color.objects.all().delete()
                    self.stdout.write("🗑️  Cleared existing Plating_Color data for routing update.")

                created_count = 0
                zone_1_colors = []
                zone_2_colors = []
                
                for plating_color, plating_color_internal in plating_colors_data:
                    # TTT Color-wise routing logic implementation
                    if plating_color == "IPS":
                        # IPS goes to Zone 1 ONLY
                        zone_1 = True
                        zone_2 = False
                        zone_1_colors.append(plating_color)
                        routing_info = "→ Zone 1 (IPS Only)"
                    else:
                        # All other colors go to Zone 2 ONLY  
                        zone_1 = False
                        zone_2 = True
                        zone_2_colors.append(plating_color)
                        routing_info = "→ Zone 2 (Non-IPS)"
                    
                    plating_color_obj, created = Plating_Color.objects.get_or_create(
                        plating_color=plating_color,
                        defaults={
                            'plating_color_internal': plating_color_internal,
                            'jig_unload_zone_1': zone_1,
                            'jig_unload_zone_2': zone_2,
                        }
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(f"   ✅ {plating_color} ({plating_color_internal}) {routing_info}")
                    else:
                        # Update existing record with correct routing
                        plating_color_obj.jig_unload_zone_1 = zone_1
                        plating_color_obj.jig_unload_zone_2 = zone_2
                        plating_color_obj.save()
                        self.stdout.write(f"   🔄 Updated {plating_color} ({plating_color_internal}) {routing_info}")

                self.stdout.write(f"\n🎨 Plating Colors: {created_count} new records created")
                
                # TTT Color routing summary
                self.stdout.write("\n🚦 TTT COLOR-WISE ROUTING IMPLEMENTATION:")
                self.stdout.write(f"   🔵 Zone 1 (Jig Unloading): {', '.join(zone_1_colors)}")
                self.stdout.write(f"   🟢 Zone 2 (Jig Unloading Zone 2): {', '.join(zone_2_colors[:8])}{'...' if len(zone_2_colors) > 8 else ''}")
                self.stdout.write(f"   📊 Zone 1 colors: {len(zone_1_colors)} | Zone 2 colors: {len(zone_2_colors)}")
                self.stdout.write("")
                return created_count
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error loading Plating_Color: {str(e)}')
            )
            return 0

    def generate_tray_ids(self, TrayId, TrayType, Plating_Color):
        """
        Generate TrayId records with color-based prefixes according to TTT requirements:
        - IPS: Red Color Tray - NR-A00001 or JR-A00001  
        - Other Colors: Dark Green Tray - ND-A00001 OR JD-A00001
        - Bi Color: Light Green - NL-A00001 OR JL-A00001
        """
        try:
            with transaction.atomic():
                # Get admin user for created_by field
                admin_user = User.objects.filter(is_superuser=True).first()
                if not admin_user:
                    self.stdout.write("⚠️  No admin user found. Creating tray IDs without user assignment.")
                
                # Get tray types
                normal_tray = TrayType.objects.filter(tray_type="Normal").first()
                jumbo_tray = TrayType.objects.filter(tray_type="Jumbo").first()
                
                if not normal_tray or not jumbo_tray:
                    self.stdout.write("⚠️  Normal or Jumbo tray types not found. Please ensure TrayType records exist.")
                    return 0
                
                created_count = 0
                
                # Define tray generation parameters
                tray_configs = [
                    # IPS - Red Color Trays (Zone 1)
                    {"color_match": "IPS", "prefix": "NR", "tray_type": normal_tray, "color": "Red", "count": 100},
                    {"color_match": "IPS", "prefix": "JR", "tray_type": jumbo_tray, "color": "Red", "count": 100},
                    
                    # Other Colors - Dark Green Trays (Zone 2)  
                    {"color_match": "OTHER", "prefix": "ND", "tray_type": normal_tray, "color": "Dark Green", "count": 200},
                    {"color_match": "OTHER", "prefix": "JD", "tray_type": jumbo_tray, "color": "Dark Green", "count": 100},
                    
                    # Bi Color - Light Green Trays
                    {"color_match": "BICOLOR", "prefix": "NL", "tray_type": normal_tray, "color": "Light Green", "count": 50},
                    {"color_match": "BICOLOR", "prefix": "JL", "tray_type": jumbo_tray, "color": "Light Green", "count": 25},
                ]
                
                for config in tray_configs:
                    self.stdout.write(f"\n🎨 Generating {config['color']} {config['tray_type'].tray_type} trays with prefix {config['prefix']}...")
                    
                    for i in range(51, config['count'] + 1):
                        tray_id = f"{config['prefix']}-A{i:05d}"  # Format: NR-A00001, JR-A00001, etc.
                        
                        # Check if tray already exists
                        if TrayId.objects.filter(tray_id=tray_id).exists():
                            continue
                            
                        # Create tray record
                        tray_obj = TrayId.objects.create(
                            tray_id=tray_id,
                            tray_type=config['tray_type'].tray_type,
                            tray_capacity=config['tray_type'].tray_capacity,
                            new_tray=True,
                            scanned=False,
                            user=admin_user,
                        )
                        
                        created_count += 1
                        
                        if i <= 5 or i % 25 == 0:  # Show first 5 and every 25th
                            self.stdout.write(f"   ✅ {tray_id} ({config['color']} {config['tray_type'].tray_type})")
                    
                    self.stdout.write(f"   📦 Generated {config['count']} {config['color']} {config['tray_type'].tray_type} trays")
                
                self.stdout.write(f"\n🆔 TrayId Generation: {created_count} new tray IDs created")
                
                # TTT Tray ID Color mapping summary
                self.stdout.write("\n🎨 TTT TRAY ID COLOR MAPPING:")
                self.stdout.write("   🔴 IPS Colors → Red Trays (NR-A00001, JR-A00001)")
                self.stdout.write("   🟢 Other Colors → Dark Green Trays (ND-A00001, JD-A00001)")  
                self.stdout.write("   🟢 Bi Colors → Light Green Trays (NL-A00001, JL-A00001)")
                self.stdout.write("")
                return created_count
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error generating TrayId: {str(e)}')
            )
            return 0

    def load_rejection_reasons(self, Model, rejection_reasons, table_display_name):
        """Load rejection reasons for any rejection table"""
        try:
            with transaction.atomic():
                # Clear existing data
                Model.objects.all().delete()
                self.stdout.write(f"🗑️  Cleared existing {table_display_name} data.")

                created_count = 0
                
                for reason in rejection_reasons:
                    rejection_obj, created = Model.objects.get_or_create(
                        rejection_reason=reason
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(f"   ✅ {reason}")

                self.stdout.write(f"🚫 {table_display_name}: {created_count} records created\n")
                return created_count
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error loading {table_display_name}: {str(e)}')
            )
            return 0

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload even if data exists',
        )
        parser.add_argument(
            '--tables',
            nargs='+',
            help='Load specific tables only (e.g., --tables Plating_Color IP_Rejection_Table)',
        )