import subprocess

# List of your apps in the order you want to run migrations
apps = [
    'modelmasterapp',
    'adminportal',
    'DayPlanning',
    'InputScreening',
    'Brass_QC',
    'BrassAudit',
    'IQF',
    'Jig_Loading',
    'Jig_Unloading',
    'JigUnloading_Zone2',
    'Inprocess_Inspection',
    'Nickel_Inspection',
    'nickel_inspection_zone_two',
    'Nickel_Audit',
    'Spider_Spindle',
    'Spider_Spindle_zone_two',
    'nickel_audit_zone_two',
    'Recovery_DP',
    'Recovery_IS',
    'Recovery_Brass_QC',
    'Recovery_BrassAudit',
    'Recovery_IQF',
    'ReportsModule'
]

for app in apps:
    print(f"\n=== Running makemigrations for {app} ===")
    subprocess.run(["python", "manage.py", "makemigrations", app])
    
    print(f"\n=== Running migrate for {app} ===")
    subprocess.run(["python", "manage.py", "migrate", app])
