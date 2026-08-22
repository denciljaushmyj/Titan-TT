from django import template

register = template.Library()

@register.filter
def color_index(model_number):
    # Use hash for stable index; mod by total color count (e.g. 10)
    return abs(hash(str(model_number))) % 4


from django import template
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get item from dictionary by key
    Usage: {{ dictionary|get_item:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

@register.filter
def get_list_item(list_obj, index):
    """
    Template filter to get item from list by index
    Usage: {{ list|get_list_item:index }}
    """
    try:
        return list_obj[int(index)]
    except (IndexError, TypeError, ValueError):
        return ''

@register.filter
def json_encode(obj):
    """
    Template filter to JSON encode objects
    Usage: {{ object|json_encode }}
    """
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return '{}'