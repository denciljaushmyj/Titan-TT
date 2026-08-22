from django.contrib import admin
from .models import *
from django import forms
from django.contrib.auth.models import Group
from .utils import extract_table_headings_from_html
import os
from bs4 import BeautifulSoup

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'templates')

def get_all_menu_titles():
    titles = set()
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                with open(path, encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                    # Find all elements with data-module-name attribute
                    for li in soup.find_all(attrs={"data-module-name": True}):
                        val = li.get("data-module-name", "").strip()
                        if val:
                            titles.add(val)
    return sorted(titles)

class ModuleAdminForm(forms.ModelForm):
    menu_title = forms.ChoiceField(
        choices=[],  # Start with empty choices
        required=False,
        help_text="Select the main menu title."
    )
    headings = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Auto-fill by selecting an HTML file below, or enter manually as a JSON list."
    )
    html_file = forms.ChoiceField(
        choices=[],  # Start with empty choices
        required=False,
        label="Extract headings from HTML file",
        help_text="Select an HTML file to auto-fill headings."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate choices dynamically when form is instantiated
        self.fields['menu_title'].choices = [('', '---------')] + [(t, t) for t in get_all_menu_titles()]
        self.fields['html_file'].choices = [('', '---------')] + [
            (os.path.relpath(os.path.join(root, file), TEMPLATES_DIR), file)
            for root, dirs, files in os.walk(TEMPLATES_DIR)
            for file in files if file.endswith('.html')
        ]

    class Meta:
        model = Module
        fields = '__all__'

    def clean_headings(self):
        data = self.cleaned_data['headings']
        import json
        if not data:
            return []
        try:
            return json.loads(data)
        except Exception:
            raise forms.ValidationError("Headings must be a valid JSON list.")
    
    def clean(self):
        cleaned_data = super().clean()
        html_file = cleaned_data.get('html_file')
        if html_file:
            abs_path = os.path.join(TEMPLATES_DIR, html_file)
            headings = extract_table_headings_from_html(abs_path)
            cleaned_data['headings'] = headings
        return cleaned_data
    class Media:
        js = ('admin/js/module_headings_autofill.js',)

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    form = ModuleAdminForm
    list_display = ('name', 'menu_title', 'parent')


@admin.register(ShortcutConfiguration)
class ShortcutConfigurationAdmin(admin.ModelAdmin):
    list_display = ('key_display', 'label', 'action_type', 'sort_order', 'is_active')
    list_filter = ('action_type', 'is_active', 'allow_in_modal', 'allow_when_typing')
    search_fields = ('code', 'key_display', 'label', 'description', 'target_selector')
    ordering = ('sort_order', 'label')

# Django Admin Panel - Department Master
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

# Django Admin Panel - Titan Role Master
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

# Django Admin Panel - User & Module Provision List
# ...existing code...

@admin.register(UserModuleProvision)
class UserModuleProvisionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'module_name', 'created_at')
    search_fields = ('user__username', 'module_name')
    list_filter = ('user', 'module_name')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        module_name = None
        if request.method == "POST":
            module_name = request.POST.get("module_name")
        elif obj:
            module_name = obj.module_name
        headings_choices = []
        initial_headings = []
        if module_name:
            from .models import Module
            try:
                mod = Module.objects.filter(name=module_name).first()
                if mod and mod.headings:
                    headings_choices = [(h, h) for h in mod.headings]
            except Exception:
                pass
        if obj and obj.headings:
            initial_headings = obj.headings
        # Dynamically replace the headings field with checkboxes
        form.base_fields['headings'] = forms.MultipleChoiceField(
            choices=headings_choices,
            required=False,
            widget=forms.CheckboxSelectMultiple,
            initial=initial_headings,
            help_text="Select accessible headings (columns) for this user/module."
        )
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .services import invalidate_user_modules_cache
        invalidate_user_modules_cache(obj.user_id)

    def delete_model(self, request, obj):
        user_id = obj.user_id
        super().delete_model(request, obj)
        from .services import invalidate_user_modules_cache
        invalidate_user_modules_cache(user_id)

    def delete_queryset(self, request, queryset):
        from .services import invalidate_user_modules_cache
        user_ids = list(queryset.values_list('user_id', flat=True).distinct())
        super().delete_queryset(request, queryset)
        for user_id in user_ids:
            invalidate_user_modules_cache(user_id)




# Django Admin Panel - User Management Table with all details
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'role', 'manager', 'employment_status')
    search_fields = ('user__username', 'user__email', 'manager')
    list_filter = ('department', 'role', 'employment_status')
    
    
