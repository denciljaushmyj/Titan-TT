from django import template
from django.templatetags.static import static as static_url
import os

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, "")


@register.simple_tag
def static_v(path):
    """
    Same as Django's {% static %}, but auto-appends a `?v=<mtime>`
    cache-busting query string derived from the source file's last-modified
    time. This means editing a static JS/CSS file always forces browsers to
    fetch the new version, without anyone needing to remember to manually
    bump a version string (a forgotten manual bump is what caused the
    Reports "Day Planning empty column" bug to look unresolved even after
    the underlying code was fixed).
    """
    url = static_url(path)
    try:
        from django.contrib.staticfiles import finders
        abs_path = finders.find(path)
        if abs_path:
            return f"{url}?v={int(os.path.getmtime(abs_path))}"
    except Exception:
        pass
    return url

