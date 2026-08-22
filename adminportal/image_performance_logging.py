"""Image/static/media performance logging helpers.

This module is diagnostics-only. It must never change image lookup, upload,
delete, static serving, or media serving behavior.
"""

from __future__ import annotations

import os
import time

from django.conf import settings
from django.http import Http404
from django.utils._os import safe_join
from django.views.static import serve as django_static_serve

from watchcase_tracker.performance_logging.logger import emit_perf_event
from watchcase_tracker.performance_logging.sanitizer import hash_value, truncate_value


DEFAULT_SLOW_IMAGE_MS = 500
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
STATIC_EXTENSIONS = {
    '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.otf', '.ico',
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
}


def perf_counter():
    try:
        return time.perf_counter()
    except Exception:
        return 0.0


def duration_ms(start):
    try:
        return round((time.perf_counter() - start) * 1000, 3)
    except Exception:
        return None


def perf_enabled():
    try:
        return bool(getattr(settings, 'PERF_LOG_ENABLED', False))
    except Exception:
        return False


def hashed_value(value, prefix='hash'):
    try:
        if value in (None, ''):
            return None
        return hash_value(str(value), prefix=prefix, length=16)
    except Exception:
        return None


def image_extension(name):
    try:
        return truncate_value(os.path.splitext(str(name or ''))[1].lower(), max_chars=20)
    except Exception:
        return ''


def asset_type(name):
    try:
        ext = image_extension(name)
        if ext in IMAGE_EXTENSIONS:
            return 'image'
        if ext in STATIC_EXTENSIONS:
            return ext.lstrip('.') or 'static'
        return 'unknown'
    except Exception:
        return 'unknown'


def storage_type(file_field):
    try:
        storage = getattr(file_field, 'storage', None)
        if storage is None:
            return None
        return truncate_value(f'{storage.__class__.__module__}.{storage.__class__.__name__}', max_chars=160)
    except Exception:
        return None


def estimated_file_size(file_field):
    try:
        if not file_field:
            return None
        return getattr(file_field, 'size', None)
    except Exception:
        return None


def file_exists(file_field):
    try:
        if not file_field:
            return False
        name = getattr(file_field, 'name', None)
        storage = getattr(file_field, 'storage', None)
        if not name or not storage:
            return False
        return bool(storage.exists(name))
    except Exception:
        return None


def slow_image_threshold_ms():
    try:
        return max(int(os.getenv('PERF_LOG_SLOW_IMAGE_MS', str(DEFAULT_SLOW_IMAGE_MS))), 1)
    except Exception:
        return DEFAULT_SLOW_IMAGE_MS


def emit_image_event(request, event_type, level, message, metadata=None):
    try:
        if not perf_enabled():
            return
        emit_perf_event(
            'IMAGE',
            event_type,
            level,
            message,
            metadata=metadata or {},
            request=request,
        )
    except Exception:
        return


def emit_slow_if_needed(request, lookup_type, elapsed_ms, metadata=None):
    try:
        if not perf_enabled():
            return
        if elapsed_ms is None or elapsed_ms <= slow_image_threshold_ms():
            return
        slow_metadata = dict(metadata or {})
        slow_metadata.update({
            'lookup_type': truncate_value(lookup_type, max_chars=80),
            'duration_ms': elapsed_ms,
            'threshold_ms': slow_image_threshold_ms(),
        })
        emit_image_event(
            request,
            'IMAGE.SLOW',
            'WARNING',
            'Image/static/media diagnostic duration exceeded threshold',
            slow_metadata,
        )
    except Exception:
        return


def emit_lookup_start(request, lookup_source, stock_no=None, model_no=None, view_requested=None):
    if not perf_enabled():
        return
    emit_image_event(
        request,
        'IMAGE.LOOKUP.START',
        'INFO',
        'Image lookup started',
        {
            'lookup_source': truncate_value(lookup_source, max_chars=120),
            'stock_hash': hashed_value(stock_no, prefix='stock') if stock_no else None,
            'model_hash': hashed_value(model_no, prefix='model') if model_no else None,
            'view_requested': truncate_value(view_requested, max_chars=80),
        },
    )


def emit_lookup_end(request, lookup_source, elapsed_ms, images_returned, model_found=True, extra=None):
    if not perf_enabled():
        return
    metadata = {
        'lookup_source': truncate_value(lookup_source, max_chars=120),
        'duration_ms': elapsed_ms,
        'images_returned': images_returned,
        'model_found': bool(model_found),
    }
    if extra:
        metadata.update(extra)
    emit_image_event(request, 'IMAGE.LOOKUP.END', 'INFO', 'Image lookup completed', metadata)
    emit_slow_if_needed(request, lookup_source, elapsed_ms, metadata)


def emit_lookup_not_found(request, lookup_source, elapsed_ms, reason_category, extra=None):
    if not perf_enabled():
        return
    metadata = {
        'lookup_source': truncate_value(lookup_source, max_chars=120),
        'duration_ms': elapsed_ms,
        'reason_category': truncate_value(reason_category, max_chars=120),
    }
    if extra:
        metadata.update(extra)
    emit_image_event(request, 'IMAGE.LOOKUP.NOT_FOUND', 'INFO', 'Image lookup returned no result', metadata)
    emit_slow_if_needed(request, lookup_source, elapsed_ms, metadata)


def emit_media_read(request, file_field, elapsed_ms=None, exists=None, lookup_source=None):
    try:
        if not perf_enabled():
            return
        started = perf_counter()
        exists_value = file_exists(file_field) if exists is None else exists
        measured_ms = duration_ms(started) if elapsed_ms is None else elapsed_ms
        metadata = {
            'file_extension': image_extension(getattr(file_field, 'name', None)),
            'estimated_size_bytes': estimated_file_size(file_field) if exists_value else None,
            'duration_ms': measured_ms,
            'exists': exists_value,
            'storage_type': storage_type(file_field),
            'lookup_source': truncate_value(lookup_source, max_chars=120),
            'media_name_hash': hashed_value(getattr(file_field, 'name', None), prefix='media'),
        }
        emit_image_event(request, 'IMAGE.MEDIA.READ', 'INFO', 'Media image metadata read', metadata)
        if exists_value is False:
            emit_lookup_not_found(
                request,
                lookup_source or 'media_file',
                measured_ms,
                'media_file_missing',
                {'media_name_hash': metadata['media_name_hash']},
            )
    except Exception:
        return


def emit_media_write(request, file_obj, elapsed_ms, result='saved'):
    try:
        if not perf_enabled():
            return
        emit_image_event(
            request,
            'IMAGE.MEDIA.WRITE',
            'INFO',
            'Media image write completed',
            {
                'duration_ms': elapsed_ms,
                'result': truncate_value(result, max_chars=80),
                'file_extension': image_extension(getattr(file_obj, 'name', None)),
                'estimated_size_bytes': getattr(file_obj, 'size', None),
                'storage_type': truncate_value(file_obj.__class__.__name__, max_chars=120),
                'content_type': truncate_value(getattr(file_obj, 'content_type', None), max_chars=120),
                'media_name_hash': hashed_value(getattr(file_obj, 'name', None), prefix='upload'),
            },
        )
        emit_slow_if_needed(request, 'media_write', elapsed_ms, {'result': result})
    except Exception:
        return


def emit_media_delete(request, file_field, elapsed_ms, result='deleted'):
    try:
        if not perf_enabled():
            return
        emit_image_event(
            request,
            'IMAGE.MEDIA.DELETE',
            'INFO',
            'Media image delete completed',
            {
                'duration_ms': elapsed_ms,
                'result': truncate_value(result, max_chars=80),
                'file_extension': image_extension(getattr(file_field, 'name', None)),
                'storage_type': storage_type(file_field),
                'media_name_hash': hashed_value(getattr(file_field, 'name', None), prefix='media'),
            },
        )
        emit_slow_if_needed(request, 'media_delete', elapsed_ms, {'result': result})
    except Exception:
        return


def emit_image_error(request, lookup_source, exc, elapsed_ms=None):
    try:
        if not perf_enabled():
            return
        emit_image_event(
            request,
            'IMAGE.ERROR',
            'ERROR',
            'Image/static/media diagnostic error observed',
            {
                'lookup_source': truncate_value(lookup_source, max_chars=120),
                'duration_ms': elapsed_ms,
                'exception_class': exc.__class__.__name__,
                'safe_message': truncate_value(str(exc), max_chars=200),
            },
        )
    except Exception:
        return


def path_exists(document_root, path):
    try:
        full_path = safe_join(document_root, path)
        return os.path.exists(full_path)
    except Exception:
        return None


def serve_logged_media(request, path, document_root=None, show_indexes=False):
    if not perf_enabled():
        return django_static_serve(
            request,
            path,
            document_root=document_root,
            show_indexes=show_indexes,
        )
    started = perf_counter()
    exists_value = path_exists(document_root or settings.MEDIA_ROOT, path)
    try:
        response = django_static_serve(
            request,
            path,
            document_root=document_root,
            show_indexes=show_indexes,
        )
        elapsed = duration_ms(started)
        emit_image_event(
            request,
            'IMAGE.MEDIA.READ',
            'INFO',
            'Django-served media file read',
            {
                'file_extension': image_extension(path),
                'estimated_size_bytes': None,
                'duration_ms': elapsed,
                'exists': exists_value,
                'storage_type': 'django.views.static.serve',
                'asset_type': asset_type(path),
                'media_name_hash': hashed_value(path, prefix='media'),
                'status_code_observed': getattr(response, 'status_code', None),
            },
        )
        emit_slow_if_needed(request, 'media_static_serve', elapsed, {'asset_type': asset_type(path)})
        return response
    except Http404 as exc:
        elapsed = duration_ms(started)
        emit_lookup_not_found(
            request,
            'django_media_serve',
            elapsed,
            'media_request_missing',
            {'media_name_hash': hashed_value(path, prefix='media'), 'file_extension': image_extension(path)},
        )
        raise
    except Exception as exc:
        emit_image_error(request, 'django_media_serve', exc, duration_ms(started))
        raise


def serve_logged_static(request, path, document_root=None, show_indexes=False):
    if not perf_enabled():
        return django_static_serve(
            request,
            path,
            document_root=document_root,
            show_indexes=show_indexes,
        )
    started = perf_counter()
    exists_value = path_exists(document_root, path)
    try:
        response = django_static_serve(
            request,
            path,
            document_root=document_root,
            show_indexes=show_indexes,
        )
        elapsed = duration_ms(started)
        emit_image_event(
            request,
            'IMAGE.STATIC.READ',
            'INFO',
            'Django-served static file read',
            {
                'static_asset_type': asset_type(path),
                'file_extension': image_extension(path),
                'duration_ms': elapsed,
                'exists': exists_value,
                'requested_asset_hash': hashed_value(path, prefix='static'),
                'status_code_observed': getattr(response, 'status_code', None),
            },
        )
        emit_slow_if_needed(request, 'static_serve', elapsed, {'static_asset_type': asset_type(path)})
        return response
    except Http404:
        elapsed = duration_ms(started)
        emit_image_event(
            request,
            'IMAGE.STATIC.MISSING',
            'INFO',
            'Django-served static file missing',
            {
                'static_asset_type': asset_type(path),
                'file_extension': image_extension(path),
                'duration_ms': elapsed,
                'requested_asset_hash': hashed_value(path, prefix='static'),
            },
        )
        emit_slow_if_needed(request, 'static_missing', elapsed, {'static_asset_type': asset_type(path)})
        raise
    except Exception as exc:
        emit_image_error(request, 'django_static_serve', exc, duration_ms(started))
        raise
