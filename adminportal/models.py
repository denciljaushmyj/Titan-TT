from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import *


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name

class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name


# Module Master Table
class Module(models.Model):
    name = models.CharField(max_length=100, unique=True)
    menu_title = models.CharField(max_length=100, blank=True, null=True)
    headings = models.JSONField(default=list, blank=True, null=True)
    # ADD THIS: Store original display names
    # heading_display_map = models.JSONField(default=dict, blank=True, null=True)
    html_file = models.CharField(max_length=255, blank=True, null=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='submenus'
    )
    groups = models.ManyToManyField(
        'auth.Group', blank=True, related_name='modules',
        help_text="User groups (User Categories) that have access to this module."
    )

    def __str__(self):
        return self.name

    def get_display_headings(self):
        """Return headings with their display names"""
        if not self.heading_display_map:
            return self.headings
        return [self.heading_display_map.get(h, h) for h in self.headings]

    class Meta:
        verbose_name = "Module Master"
        verbose_name_plural = "Module Masters"


class ShortcutConfiguration(models.Model):
    ACTION_TYPE_CHOICES = [
        ('builtin', 'Built-in'),
        ('row_action', 'Row action'),
        ('row_or_page_action', 'Row or page action'),
        ('page_action', 'Page action'),
        ('focus', 'Focus element'),
    ]

    code = models.SlugField(max_length=80, unique=True)
    keys = models.JSONField(default=list, help_text="Keyboard keys that trigger this shortcut.")
    key_display = models.CharField(max_length=50)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    action_type = models.CharField(max_length=30, choices=ACTION_TYPE_CHOICES)
    target_selector = models.TextField(blank=True)
    fallback_selector = models.TextField(blank=True)
    contexts = models.JSONField(default=list, blank=True, help_text="Path fragments or 'global'.")
    allow_in_modal = models.BooleanField(default=False)
    allow_when_typing = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if not isinstance(self.keys, list) or not self.keys:
            raise ValidationError({'keys': 'At least one key is required.'})
        if self.contexts and not isinstance(self.contexts, list):
            raise ValidationError({'contexts': 'Contexts must be a list.'})

    def __str__(self):
        return f"{self.key_display} - {self.label}"

    class Meta:
        ordering = ['sort_order', 'label', 'code']
        indexes = [
            models.Index(fields=['is_active', 'sort_order'], name='shortcut_active_sort_idx'),
            models.Index(fields=['code'], name='shortcut_code_idx'),
        ]
        verbose_name = "Shortcut Configuration"
        verbose_name_plural = "Shortcut Configurations"
  

# User Module Provision Table
class UserModuleProvision(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_provisions')
    module_name = models.CharField(max_length=255)
    headings = models.JSONField(default=list, blank=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)  # <-- Add this line
    created_at = models.DateTimeField(auto_now_add=True)
    
    

    def __str__(self):
        return f"{self.user.username} - {self.module_name}"
    
    


class UserManagementTable(models.Model):
    """
    This model is for Django admin panel display only.
    It does not create a new table, but allows you to register a custom admin list.
    """
    class Meta:
        managed = False
        verbose_name = "User Management Table"
        verbose_name_plural = "User Management Table"

    @property
    def user_id(self):
        return self.user.id

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}"

    @property
    def email(self):
        return self.user.email

    @property
    def department(self):
        try:
            return self.user.userprofile.department.name
        except Exception:
            return ""

    @property
    def role(self):
        try:
            return self.user.userprofile.role.name
        except Exception:
            return ""

    @property
    def manager(self):
        try:
            return self.user.userprofile.manager
        except Exception:
            return ""

    @property
    def status(self):
        try:
            return self.user.userprofile.employment_status
        except Exception:
            return ""

    @property
    def modules(self):
        return ", ".join(
            UserModuleProvision.objects.filter(user=self.user).values_list("module_name", flat=True)
        )

    @property
    def created(self):
        return self.user.date_joined

    @property
    def actions(self):
        return "Edit/Delete"

# ...existing code...

class AccountLockout(models.Model):
    """
    Tracks consecutive failed login attempts per user and the resulting
    account lock state. Enforced by adminportal.auth_backends.AccountLockoutBackend.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_lockout')
    failed_attempts = models.PositiveIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='account_unlocks_performed'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account Lockout"
        verbose_name_plural = "Account Lockouts"
        indexes = [
            models.Index(fields=['is_locked'], name='acct_lockout_locked_idx'),
        ]

    def __str__(self):
        state = 'LOCKED' if self.is_locked else 'active'
        return f"{self.user.username} ({state}, {self.failed_attempts} failed attempts)"


class UserActiveSession(models.Model):
    """
    Single-session-per-account enforcement (TASK 1: model definition only).

    Stores the most recent valid Django session key for a user. Will be used
    to detect and reject stale sessions when the same account logs in again
    from a different browser/device, once the corresponding signals and
    middleware are added in a later task.

    Deliberately kept as its own model rather than added to `UserProfile`:
    `UserProfile` holds HR/profile data (department, role, manager,
    employment status) and is created via a post_save signal on User
    creation. Session security state should not be coupled to that, and
    keeping it separate also keeps the optional audit fields below
    (ip_address, user_agent, login_source) out of profile data.

    NOTE: No signals, middleware, or settings wiring are introduced by this
    change. The model is not yet read or written anywhere; that is handled
    in a subsequent task.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='active_session'
    )
    session_key = models.CharField(max_length=40, db_index=True)
    login_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional audit fields. Not yet populated by any code path; reserved
    # for future use (e.g. recording where/how the active session was set).
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    login_source = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "User Active Session"
        verbose_name_plural = "User Active Sessions"

    def __str__(self):
        return f"{self.user.username} -> session {self.session_key}"


from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)
    manager = models.CharField(max_length=100, blank=True, null=True)
    employment_status = models.CharField(max_length=20, choices=[('On-role', 'On-role'), ('Off-role', 'Off-role')])

    def __str__(self):
        return self.user.username

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)