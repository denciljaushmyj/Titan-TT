"""Startup and server diagnostics for the unified performance log.

This module is diagnostics-only. It must not change startup behavior, routing,
middleware order, signal registration, or application execution.
"""

from __future__ import annotations

import os
import platform
import sys
import threading
import time

from django.conf import settings

from .logger import emit_perf_event
from .sanitizer import hash_value, truncate_value


_PROCESS_STARTED_AT = time.time()
_STARTUP_SERVER_EMITTED = False
_STARTUP_SERVER_LOCK = threading.Lock()


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


def _safe(value, max_chars=120):
    try:
        return truncate_value(value, max_chars=max_chars)
    except Exception:
        return None


def _hash(value, prefix='hash'):
    try:
        if value in (None, ''):
            return None
        return hash_value(value, prefix=prefix, length=16)
    except Exception:
        return None


def _server_name():
    try:
        return _safe(platform.node() or os.getenv('COMPUTERNAME') or os.getenv('HOSTNAME'), 120)
    except Exception:
        return None


def _environment_name():
    try:
        return _safe(os.getenv('DJANGO_ENV') or os.getenv('ENVIRONMENT') or ('development' if settings.DEBUG else 'production'), 80)
    except Exception:
        return None


def _django_version():
    try:
        import django

        return _safe(django.get_version(), 40)
    except Exception:
        return None


def _is_iis_like():
    try:
        keys = ('APP_POOL_ID', 'APPL_PHYSICAL_PATH', 'IIS_SITE_NAME', 'WEBSITE_SITE_NAME')
        return any(os.getenv(key) for key in keys)
    except Exception:
        return False


def _server_type_hint():
    try:
        if _is_iis_like():
            return 'iis'
        if any('runserver' in str(arg).lower() for arg in sys.argv):
            return 'runserver'
        return 'unknown'
    except Exception:
        return 'unknown'


def _argv_summary():
    try:
        return {
            'argc': len(sys.argv),
            'has_runserver': any('runserver' in str(arg).lower() for arg in sys.argv),
            'has_manage_py': any('manage.py' in str(arg).lower() for arg in sys.argv),
            'argv_hash': _hash('|'.join(str(arg) for arg in sys.argv), prefix='argv'),
        }
    except Exception:
        return {}


def _path_category(path_value):
    try:
        if not path_value:
            return None
        base_dir = getattr(settings, 'BASE_DIR', None)
        path_text = str(path_value)
        if base_dir and path_text.lower().startswith(str(base_dir).lower()):
            return 'project'
        return 'external'
    except Exception:
        return 'unknown'


def _log_path_metadata():
    try:
        log_path = getattr(settings, 'PERF_LOG_PATH', None)
        log_dir = getattr(settings, 'PERF_LOG_DIR_RESOLVED', None)
        configured_dir = getattr(settings, 'PERF_LOG_DIR', None)
        exists = bool(log_dir and os.path.isdir(log_dir))
        writable = False
        if log_dir and exists:
            writable = os.access(log_dir, os.W_OK)
        return {
            'log_dir_configured_hash': _hash(configured_dir, prefix='logdir') if configured_dir else None,
            'log_path_category': _path_category(log_path),
            'log_dir_exists': exists,
            'log_dir_writable': writable,
            'rotation_configured': bool(getattr(settings, 'PERF_LOG_MAX_SIZE', None)),
            'backup_count': getattr(settings, 'PERF_LOG_BACKUP_COUNT', None),
        }
    except Exception:
        return {'log_path_check_error': True}


def _process_metadata():
    try:
        return {
            'process_id': os.getpid(),
            'parent_process_id': os.getppid() if hasattr(os, 'getppid') else None,
            'thread_id': threading.get_ident(),
            'thread_name': _safe(threading.current_thread().name, 80),
            'server_name': _server_name(),
            'cwd_category': _path_category(os.getcwd()),
            'cwd_hash': _hash(os.getcwd(), prefix='cwd'),
            'argv': _argv_summary(),
        }
    except Exception:
        return {}


def emit_startup_event(event_type, level='INFO', message=None, metadata=None):
    try:
        if not perf_enabled():
            return
        emit_perf_event(
            'STARTUP' if str(event_type).startswith('STARTUP.') else 'SERVER',
            event_type,
            level,
            message or event_type,
            metadata=metadata or {},
        )
    except Exception:
        return


def emit_startup_server_once():
    global _STARTUP_SERVER_EMITTED
    try:
        if not perf_enabled():
            return
        with _STARTUP_SERVER_LOCK:
            if _STARTUP_SERVER_EMITTED:
                return
            _STARTUP_SERVER_EMITTED = True
        metadata = {
            'process_id': os.getpid(),
            'thread_id': threading.get_ident(),
            'server_name': _server_name(),
            'environment': _environment_name(),
            'debug': bool(getattr(settings, 'DEBUG', False)),
            'python_version': _safe(platform.python_version(), 40),
            'django_version': _django_version(),
            'app_start_time_epoch': round(_PROCESS_STARTED_AT, 3),
        }
        emit_startup_event('STARTUP.SERVER', message='Django process startup diagnostics', metadata=metadata)
        emit_server_process()
        emit_server_environment()
        emit_log_path_check()
        emit_app_pool_recycle_hint()
    except Exception:
        return


def emit_server_process():
    if not perf_enabled():
        return
    emit_startup_event('SERVER.PROCESS', message='Server process diagnostics', metadata=_process_metadata())


def emit_server_environment():
    try:
        if not perf_enabled():
            return
        metadata = {
            'debug': bool(getattr(settings, 'DEBUG', False)),
            'django_env': _safe(os.getenv('DJANGO_ENV') or os.getenv('ENVIRONMENT'), 80),
            'server_type_hint': _server_type_hint(),
            'is_iis_like': _is_iis_like(),
            'runserver': any('runserver' in str(arg).lower() for arg in sys.argv),
            'settings_module_hash': _hash(os.getenv('DJANGO_SETTINGS_MODULE'), prefix='settings'),
        }
        emit_startup_event('SERVER.ENVIRONMENT', message='Safe server environment summary', metadata=metadata)
    except Exception:
        return


def emit_log_path_check():
    if not perf_enabled():
        return
    emit_startup_event('SERVER.LOG_PATH_CHECK', message='Performance log path check', metadata=_log_path_metadata())


def emit_app_pool_recycle_hint():
    try:
        if not perf_enabled():
            return
        metadata = {
            'process_id': os.getpid(),
            'app_start_time_epoch': round(_PROCESS_STARTED_AT, 3),
            'is_iis_like': _is_iis_like(),
            'app_pool_hash': _hash(os.getenv('APP_POOL_ID'), prefix='apppool') if os.getenv('APP_POOL_ID') else None,
            'persistent_marker_used': False,
        }
        emit_startup_event('SERVER.APP_POOL_RECYCLE', message='Process restart/recycle hint', metadata=metadata)
    except Exception:
        return


def emit_app_ready_start():
    if not perf_enabled():
        return
    emit_startup_event('STARTUP.APP_READY', message='AppConfig.ready started', metadata={'phase': 'start'})


def emit_app_ready_end(duration, success=True):
    if not perf_enabled():
        return
    emit_startup_event(
        'STARTUP.APP_READY',
        level='INFO' if success else 'ERROR',
        message='AppConfig.ready completed',
        metadata={'phase': 'end', 'duration_ms': duration, 'success': bool(success)},
    )


def emit_signals_registered(duration, success=True):
    if not perf_enabled():
        return
    emit_startup_event(
        'STARTUP.SIGNALS_REGISTERED',
        level='INFO' if success else 'ERROR',
        message='Django signals registration completed',
        metadata={'duration_ms': duration, 'success': bool(success)},
    )


def emit_urlconf_loaded(duration, urlpattern_count=None):
    if not perf_enabled():
        return
    emit_startup_event(
        'STARTUP.URLCONF',
        message='URLConf loaded',
        metadata={'duration_ms': duration, 'urlpattern_count': urlpattern_count},
    )


def emit_wsgi_event(phase, duration=None):
    if not perf_enabled():
        return
    emit_startup_event(
        'STARTUP.WSGI',
        message='WSGI startup diagnostic',
        metadata={'phase': _safe(phase, 40), 'duration_ms': duration},
    )


def emit_asgi_event(phase, duration=None):
    if not perf_enabled():
        return
    emit_startup_event(
        'STARTUP.ASGI',
        message='ASGI startup diagnostic',
        metadata={'phase': _safe(phase, 40), 'duration_ms': duration},
    )
