"""
Shared helper for resolving which ModelImage should be treated as a
model's "Front View" when a view/template needs a single representative
image (e.g. the plating-stock-number hover preview).

ModelImage records are tagged only by filename convention
(<model_no>xx<bath_code><version><VIEW_SUFFIX>.ext, e.g. "1805xxd02FV.jpg").
The M2M ModelMaster.images has no ordering guarantee, so naively taking
images.all()[0] can surface a Top View / Isometric View / Side View instead
of the Front View. This module centralizes the view-code detection so every
module reuses the same rule instead of re-implementing "first image wins".
"""

import os
import re

# Front View wins; Front-Side View is the closest available substitute when
# a model has no dedicated FV upload yet.
_FRONT_VIEW_PREFERENCE = ('FV', 'FSV')
MODEL_VIEW_SEQUENCE = ('FV', 'TV', 'IV', 'RSV')
NO_IMAGE_VIEW_CODE = 'NO_IMAGE'

_VIEW_SUFFIXES = ('RSV', 'LSV', 'FSV', 'TV', 'FV', 'IV', 'BV')
_NO_IMAGE_FILENAMES = ('NO_IMAGE', 'NOIMAGE')
_STOCK_NO_CANONICAL_RE = re.compile(r'(\d{4})([A-Z])([A-Z])([A-Z])(\d{2})', re.IGNORECASE)
_IMAGE_KEY_RE = re.compile(r'^(?P<image_key>\d{4}[A-Z0-9]{3}\d{2})$', re.IGNORECASE)


def get_model_image_lookup_name(img):
    return (
        getattr(img, 'original_filename', '')
        or getattr(getattr(img, 'master_image', None), 'name', '')
        or ''
    )


def detect_image_type(name):
    """Return FV/TV/IV/RSV/NO_IMAGE from an image filename, or None."""
    base_name = os.path.splitext(os.path.basename(name or ''))[0].upper()
    normalized_name = base_name.replace('-', '_').replace(' ', '_')
    compact_name = normalized_name.replace('_', '')
    if 'NO_IMAGE' in normalized_name or compact_name in _NO_IMAGE_FILENAMES:
        return NO_IMAGE_VIEW_CODE

    for suffix in _VIEW_SUFFIXES:
        if base_name.endswith(suffix) or base_name.endswith('_' + suffix):
            return suffix
    return None


def detect_image_view(name):
    """Return the view-code suffix (e.g. 'FV') found in an image filename, or None."""
    image_type = detect_image_type(name)
    if image_type == NO_IMAGE_VIEW_CODE:
        return None
    return image_type


def build_model_image_keys_from_stock(plating_stock_no):
    """
    Return exact filename-family keys for a plating stock number.

    Newer uploads may include the stock polish/plating family
    (<model><polish>x<plating><version>). Older project uploads use the
    established generic family (<model>xx<bath><version>). Both are exact
    filename-family keys; neither falls back to the base model number alone.
    """
    stock_no = str(plating_stock_no or '').strip().upper()
    match = _STOCK_NO_CANONICAL_RE.search(stock_no)
    if not match:
        return ()

    model_no, polish_code, plating_code, bath_code, version_code = match.groups()
    keys = (
        f'{model_no}{polish_code.lower()}x{plating_code.lower()}{version_code}',
        f'{model_no}xx{bath_code.lower()}{version_code}',
    )
    return tuple(dict.fromkeys(keys))


def build_model_image_key_from_filename(filename):
    """Return the exact filename-family key from an uploaded model image name."""
    base_name = os.path.splitext(os.path.basename(filename or ''))[0].upper()
    if detect_image_type(base_name) == NO_IMAGE_VIEW_CODE:
        return ''

    view_code = detect_image_view(base_name)
    if view_code and base_name.endswith('_' + view_code):
        base_name = base_name[:-(len(view_code) + 1)]
    elif view_code and base_name.endswith(view_code):
        base_name = base_name[:-len(view_code)]

    match = _IMAGE_KEY_RE.match(base_name)
    if not match:
        return ''

    return match.group('image_key').lower()


def _valid_model_images(images):
    return [
        img
        for img in images
        if get_image_url(img)
    ]


def get_image_url(image_obj):
    """Return a browser-accessible URL for a ModelImage, or None if unusable."""
    if not image_obj:
        return None

    image_field = getattr(image_obj, 'master_image', None)
    image_name = getattr(image_field, 'name', '')
    if not image_field or not image_name:
        return None

    try:
        if hasattr(image_field, 'storage') and not image_field.storage.exists(image_name):
            return None
    except Exception:
        return None

    try:
        return image_field.url
    except Exception:
        return None


def _is_no_image_name(filename):
    base_name = os.path.splitext(os.path.basename(filename or ''))[0]
    normalized_name = base_name.replace('-', '_').replace(' ', '_').lower()
    compact_name = normalized_name.replace('_', '')
    return normalized_name == 'no_image' or compact_name == 'noimage'


def get_global_no_image():
    """Return the global no_image ModelImage, independent of any model links."""
    from modelmasterapp.models import ModelImage

    for img in ModelImage.objects.all().only('id', 'master_image', 'original_filename'):
        lookup_name = get_model_image_lookup_name(img)
        storage_name = getattr(getattr(img, 'master_image', None), 'name', '')
        if (_is_no_image_name(lookup_name) or _is_no_image_name(storage_name)) and get_image_url(img):
            return img
    return None


def get_no_image(images):
    """Return the uploaded no_image ModelImage from an iterable, if present."""
    for img in _valid_model_images(images):
        lookup_name = get_model_image_lookup_name(img)
        storage_name = getattr(getattr(img, 'master_image', None), 'name', '')
        if _is_no_image_name(lookup_name) or _is_no_image_name(storage_name):
            return img
    return None


def is_no_image_model_image(image_obj):
    """Return True when a ModelImage represents the shared no-image placeholder."""
    if not image_obj:
        return False

    lookup_name = get_model_image_lookup_name(image_obj)
    storage_name = getattr(getattr(image_obj, 'master_image', None), 'name', '')
    return _is_no_image_name(lookup_name) or _is_no_image_name(storage_name)


def get_image_by_view(images, view_code):
    """Return the exact uploaded image for a requested view, never another view."""
    requested_view = str(view_code or '').strip().upper()
    if requested_view not in MODEL_VIEW_SEQUENCE:
        return None

    for img in _valid_model_images(images):
        if detect_image_type(get_model_image_lookup_name(img)) == requested_view:
            return img
    return None


def get_image_or_placeholder(images, view_code):
    """
    Return requested view -> linked no_image -> global no_image -> None.

    This is the only supported fallback rule for view-specific model images.
    """
    images = list(images)
    return get_image_by_view(images, view_code) or get_no_image(images) or get_global_no_image()


def get_model_view_images(images, view_sequence=MODEL_VIEW_SEQUENCE):
    """
    Return one image per requested view using requested view -> no_image -> None.

    The result preserves the requested sequence and never substitutes FV/TV/IV/RSV
    for each other.
    """
    images = list(images)
    resolved = []
    for view_code in view_sequence:
        img = get_image_or_placeholder(images, view_code)
        if img:
            resolved.append(img)
    return resolved


def get_model_view_image_urls(images, view_sequence=MODEL_VIEW_SEQUENCE):
    return [
        image_url
        for img in get_model_view_images(images, view_sequence=view_sequence)
        for image_url in [get_image_url(img)]
        if image_url
    ]


def get_uploaded_model_image_urls(images):
    """Return URLs for the actual uploaded images, excluding no-image placeholders."""
    urls = []
    for img in _valid_model_images(images):
        if is_no_image_model_image(img):
            continue

        image_url = get_image_url(img)
        if image_url:
            urls.append(image_url)

    return urls


def sort_images_front_first(images):
    """
    Reorder an iterable of ModelImage objects so the Front View (or the
    closest available substitute) comes first. All images are kept and
    their relative order among themselves is otherwise preserved -
    this only moves the front-view candidate to the front.
    """
    images = [
        img
        for img in images
        if detect_image_type(get_model_image_lookup_name(img)) != NO_IMAGE_VIEW_CODE
    ]

    for view_code in _FRONT_VIEW_PREFERENCE:
        for img in images:
            lookup_name = get_model_image_lookup_name(img)
            if detect_image_view(lookup_name) == view_code:
                return [img] + [other for other in images if other is not img]

    return images
