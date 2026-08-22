import os
import glob
import subprocess
import django
import psycopg2
from django.conf import settings

# Setup Django settings (update project name!)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "watchcase_tracker.settings")
django.setup()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("🧹 Deleting old migration files...")
for root, dirs, files in os.walk(BASE_DIR):
    if "migrations" in dirs:
        mig_path = os.path.join(root, "migrations")
        for f in glob.glob(os.path.join(mig_path, "*.py")):
            if not f.endswith("__init__.py"):
                os.remove(f)
        for f in glob.glob(os.path.join(mig_path, "*.pyc")):
            os.remove(f)

db_settings = settings.DATABASES["default"]

print("🗑️ Dropping PostgreSQL database...")
conn = psycopg2.connect(
    dbname="postgres",   # connect to default db first
    user=db_settings["USER"],
    password=db_settings["PASSWORD"],
    host=db_settings["HOST"],
    port=db_settings["PORT"],
)
conn.autocommit = True
cur = conn.cursor()

# terminate active connections
cur.execute(f"""
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = '{db_settings['NAME']}';
""")

# drop + recreate db
cur.execute(f"DROP DATABASE IF EXISTS {db_settings['NAME']}")
cur.execute(f"CREATE DATABASE {db_settings['NAME']}")
cur.close()
conn.close()
print(f"✅ Database {db_settings['NAME']} dropped and recreated")

print("⚙️ Creating fresh migrations for all apps...")
subprocess.call(["python", "manage.py", "makemigrations"] + [
    "modelmasterapp", "adminportal", "DayPlanning", "InputScreening",
    "Brass_QC", "BrassAudit", "IQF", "Jig_Loading", "Jig_Unloading",
    "JigUnloading_Zone2", "Inprocess_Inspection", "Nickel_Inspection",
    "nickel_inspection_zone_two", "Nickel_Audit", "Spider_Spindle",
    "Spider_Spindle_zone_two", "nickel_audit_zone_two", "Recovery_DP",
    "Recovery_IS", "Recovery_Brass_QC", "Recovery_BrassAudit",
    "Recovery_IQF", "ReportsModule"
])

print("⚙️ Applying migrations for all apps...")
subprocess.call(["python", "manage.py", "migrate", "--run-syncdb"])

# Ensure sessions table is created
subprocess.call(["python", "manage.py", "migrate", "sessions"])

print("🚀 Starting development server...")

# Create Django superuser before running the server
subprocess.call(["python", "manage.py", "createsuperuser"])

subprocess.call(["python", "manage.py", "runserver"])

print("🎉 Done! Fresh DB + migrations ready and server running ✅")