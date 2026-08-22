"""Service, cache, thread, background, and external diagnostics helpers.

This module is observability-only. It must never change service execution,
cache behavior, thread lifecycle, or external dependency behavior.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import caches

from watchcase_tracker.performance_logging.logger import emit_perf_event
from watchcase_tracker.performance_logging.sanitizer import hash_value, truncate_value


DEFAULT_SLOW_SERVICE_MS = 750


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


def slow_service_threshold_ms():
    try:
        return max(int(os.getenv('PERF_LOG_SLOW_SERVICE_MS', str(DEFAULT_SLOW_SERVICE_MS))), 1)
    except Exception:
        return DEFAULT_SLOW_SERVICE_MS


def safe_text(value, max_chars=120):
    try:
        return truncate_value(value, max_chars=max_chars)
    except Exception:
        return None


def safe_hash(value, prefix='hash'):
    try:
        if value in (None, ''):
            return None
        return hash_value(str(value), prefix=prefix, length=16)
    except Exception:
        return None


def cache_backend(alias='default'):
    try:
        backend = caches[alias]
        return safe_text(f'{backend.__class__.__module__}.{backend.__class__.__name__}', 160)
    except Exception:
        return None


def cache_key_hashes(keys):
    try:
        if isinstance(keys, dict):
            keys = keys.values()
        if isinstance(keys, (list, tuple, set)):
            return [safe_hash(key, prefix='cache') for key in list(keys)[:50]]
        return safe_hash(keys, prefix='cache')
    except Exception:
        return None


def estimate_size(value):
    try:
        if value is None:
            return 0
        if isinstance(value, dict):
            return len(value)
        if isinstance(value, (list, tuple, set)):
            return len(value)
        if isinstance(value, (str, bytes, bytearray)):
            return len(value)
        return None
    except Exception:
        return None


def emit_diag_event(event_type, level, message, metadata=None, request=None):
    try:
        if not perf_enabled():
            return
        event_category = str(event_type or 'SERVICE').split('.', 1)[0]
        emit_perf_event(
            event_category,
            event_type,
            level,
            message,
            metadata=metadata or {},
            request=request,
        )
    except Exception:
        return


def emit_service_start(service_name, caller=None, request=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'service_name': safe_text(service_name),
        'caller': safe_text(caller),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('SERVICE.START', 'INFO', 'Service execution started', data, request=request)


def emit_service_end(service_name, duration, success=True, caller=None, request=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'service_name': safe_text(service_name),
        'caller': safe_text(caller),
        'duration_ms': duration,
        'success': bool(success),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('SERVICE.END', 'INFO', 'Service execution completed', data, request=request)
    emit_service_slow(service_name, duration, caller=caller, request=request, metadata=metadata)


def emit_service_slow(service_name, duration, caller=None, request=None, metadata=None):
    try:
        if not perf_enabled():
            return
        if duration is None or duration <= slow_service_threshold_ms():
            return
        data = {
            'service_name': safe_text(service_name),
            'caller': safe_text(caller),
            'duration_ms': duration,
            'threshold_ms': slow_service_threshold_ms(),
        }
        if metadata:
            data.update(metadata)
        emit_diag_event('SERVICE.SLOW', 'WARNING', 'Service execution exceeded threshold', data, request=request)
    except Exception:
        return


def emit_service_error(service_name, exc, duration=None, caller=None, request=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'service_name': safe_text(service_name),
        'caller': safe_text(caller),
        'duration_ms': duration,
        'exception_class': exc.__class__.__name__,
        'safe_message': safe_text(str(exc), 200),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('SERVICE.ERROR', 'ERROR', 'Service execution failed', data, request=request)


@contextmanager
def service_timer(service_name, caller=None, request=None, metadata=None):
    started = perf_counter()
    emit_service_start(service_name, caller=caller, request=request, metadata=metadata)
    try:
        yield
    except Exception as exc:
        elapsed = duration_ms(started)
        emit_service_error(service_name, exc, duration=elapsed, caller=caller, request=request, metadata=metadata)
        raise
    else:
        elapsed = duration_ms(started)
        emit_service_end(service_name, elapsed, success=True, caller=caller, request=request, metadata=metadata)


def emit_cache_event(event_type, operation, cache_keys=None, duration=None, hit=None, size=None, alias='default', metadata=None):
    if not perf_enabled():
        return
    data = {
        'operation': safe_text(operation),
        'cache_key_hash': cache_key_hashes(cache_keys),
        'duration_ms': duration,
        'backend': cache_backend(alias),
        'hit': hit,
        'size_estimate': size,
    }
    if metadata:
        data.update(metadata)
    emit_diag_event(event_type, 'INFO', 'Cache operation observed', data)


def emit_cache_get(operation, cache_keys, duration, hit=None, size=None, metadata=None):
    if not perf_enabled():
        return
    emit_cache_event('CACHE.GET', operation, cache_keys, duration, hit=hit, size=size, metadata=metadata)
    if hit is True:
        emit_cache_event('CACHE.HIT', operation, cache_keys, duration, hit=True, size=size, metadata=metadata)
    elif hit is False:
        emit_cache_event('CACHE.MISS', operation, cache_keys, duration, hit=False, size=size, metadata=metadata)


def emit_cache_set(operation, cache_keys, duration, size=None, metadata=None):
    if not perf_enabled():
        return
    emit_cache_event('CACHE.SET', operation, cache_keys, duration, size=size, metadata=metadata)


def emit_cache_delete(operation, cache_keys, duration, metadata=None):
    if not perf_enabled():
        return
    emit_cache_event('CACHE.DELETE', operation, cache_keys, duration, metadata=metadata)


def emit_cache_expire(operation, cache_keys, duration, metadata=None):
    if not perf_enabled():
        return
    emit_cache_event('CACHE.EXPIRE', operation, cache_keys, duration, metadata=metadata)


def emit_thread_start(thread_name=None, parent_request_id=None, metadata=None):
    if not perf_enabled():
        return
    thread = threading.current_thread()
    data = {
        'thread_id': threading.get_ident(),
        'thread_name': safe_text(thread_name or thread.name),
        'parent_request_id': safe_text(parent_request_id),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('THREAD.START', 'INFO', 'Thread execution started', data)


def emit_thread_end(thread_name=None, duration=None, result=None, metadata=None):
    if not perf_enabled():
        return
    thread = threading.current_thread()
    data = {
        'thread_id': threading.get_ident(),
        'thread_name': safe_text(thread_name or thread.name),
        'duration_ms': duration,
        'result': safe_text(result, 120),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('THREAD.END', 'INFO', 'Thread execution completed', data)


def emit_thread_error(thread_name, exc, duration=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'thread_id': threading.get_ident(),
        'thread_name': safe_text(thread_name or threading.current_thread().name),
        'duration_ms': duration,
        'exception_class': exc.__class__.__name__,
        'safe_message': safe_text(str(exc), 200),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('THREAD.ERROR', 'ERROR', 'Thread execution failed', data)


def emit_background_start(task_name, trigger=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'task_name': safe_text(task_name),
        'trigger': safe_text(trigger),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('BACKGROUND.START', 'INFO', 'Background task started', data)


def emit_background_end(task_name, duration=None, result=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'task_name': safe_text(task_name),
        'duration_ms': duration,
        'result': safe_text(result, 120),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('BACKGROUND.END', 'INFO', 'Background task completed', data)


def emit_background_error(task_name, exc, duration=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'task_name': safe_text(task_name),
        'duration_ms': duration,
        'exception_class': exc.__class__.__name__,
        'safe_message': safe_text(str(exc), 200),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('BACKGROUND.ERROR', 'ERROR', 'Background task failed', data)


def emit_external_start(target_type, target=None, operation=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'target_type': safe_text(target_type),
        'target_hash': safe_hash(target, prefix='external') if target else None,
        'operation': safe_text(operation),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('EXTERNAL.REQUEST.START', 'INFO', 'External dependency request started', data)


def emit_external_end(target_type, duration=None, status=None, target=None, operation=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'target_type': safe_text(target_type),
        'target_hash': safe_hash(target, prefix='external') if target else None,
        'operation': safe_text(operation),
        'duration_ms': duration,
        'status': safe_text(status, 80),
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('EXTERNAL.REQUEST.END', 'INFO', 'External dependency request completed', data)


def emit_external_error(target_type, exc, duration=None, target=None, operation=None, metadata=None):
    if not perf_enabled():
        return
    data = {
        'target_type': safe_text(target_type),
        'target_hash': safe_hash(target, prefix='external') if target else None,
        'operation': safe_text(operation),
        'duration_ms': duration,
        'exception_class': exc.__class__.__name__,
        'safe_message': 'External dependency request failed',
    }
    if metadata:
        data.update(metadata)
    emit_diag_event('EXTERNAL.REQUEST.ERROR', 'ERROR', 'External dependency request failed', data)
