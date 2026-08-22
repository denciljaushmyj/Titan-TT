import os, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from django.contrib.auth.models import User

password = os.environ.get('ADMIN_PASSWORD')
if not password:
    raise Exception("ADMIN_PASSWORD environment variable is not set. Refusing to run without an explicit password.")

username = os.environ.get('ADMIN_USERNAME', 'admin')

try:
    u = User.objects.get(username=username)
    u.set_password(password)
    u.save()
    print(f"Password updated successfully for user: {username}")
except User.DoesNotExist:
    raise Exception(f"User '{username}' does not exist. Create the user first.")
