import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render

LOG_PAGE_SIZE = 100
READ_CHUNK_SIZE = 8192
MAX_TAIL_BYTES = 2 * 1024 * 1024
SELF_REQUEST_PATH = '/performance-logs/'

FILTERS = {
    'all': {'label': 'All', 'icon': '', 'class': 'all'},
    'errors': {'label': 'Errors', 'icon': '🔴', 'class': 'errors'},
    'slow': {'label': 'Slow', 'icon': '🟡', 'class': 'slow'},
    'db': {'label': 'Database', 'icon': '🔵', 'class': 'db'},
    'login': {'label': 'Login', 'icon': '🟢', 'class': 'login'},
    'reports': {'label': 'Reports', 'icon': '🟣', 'class': 'reports'},
    'images': {'label': 'Images', 'icon': '🟤', 'class': 'images'},
}


def performance_logs_view(request):
    if not can_view_performance_logs(request):
        raise Http404

    selected_filter = normalize_filter(request.GET.get('filter', 'all'))
    before = normalize_before(request.GET.get('before'))
    log_path = get_performance_log_path()
    lines, next_before, has_more, read_error = read_previous_log_lines(
        log_path,
        before=before,
        limit=LOG_PAGE_SIZE,
    )
    rows, invalid_count = parse_log_lines(lines, selected_filter)
    summary, summary_invalid_count = build_log_summary(lines)
    viewer_token_query = _viewer_token_query(request)

    if request.GET.get('partial') == '1':
        return JsonResponse(
            {
                'rows': rows,
                'next_before': next_before,
                'has_more': has_more,
                'invalid_count': invalid_count,
                'loaded_line_count': len(lines),
                'read_error': read_error,
            }
        )

    return render(
        request,
        'AdminPortal/performance_logs.html',
        {
            'rows': rows,
            'filters': FILTERS,
            'selected_filter': selected_filter,
            'selected_filter_label': FILTERS[selected_filter]['label'],
            'page_size': LOG_PAGE_SIZE,
            'next_before': next_before,
            'has_more': has_more,
            'invalid_count': invalid_count,
            'read_error': read_error,
            'log_file_name': log_path.name,
            'log_file_size': log_file_size_label(log_path),
            'loaded_line_count': len(lines),
            'summary': summary,
            'summary_invalid_count': summary_invalid_count,
            'viewer_token_query': viewer_token_query,
        },
    )


def can_view_performance_logs(request):
    if getattr(settings, 'DEBUG', False):
        return True
    if _is_local_request(request):
        return True
    if not _env_bool('PERF_LOG_VIEWER_ENABLED', False):
        return False

    expected_token = os.getenv('PERF_LOG_VIEWER_TOKEN', '').strip()
    supplied_token = request.GET.get('token', '').strip()
    if not expected_token or not supplied_token:
        return False
    return secrets.compare_digest(supplied_token, expected_token)


def get_performance_log_path():
    configured_path = getattr(settings, 'PERF_LOG_PATH', None)
    if configured_path:
        return Path(configured_path)

    log_dir = getattr(settings, 'PERF_LOG_DIR_RESOLVED', None)
    if log_dir:
        return Path(log_dir) / getattr(settings, 'PERF_LOG_FILE', 'server_performance.log')

    configured_dir = Path(getattr(settings, 'PERF_LOG_DIR', 'logs')).expanduser()
    if not configured_dir.is_absolute():
        configured_dir = Path(settings.BASE_DIR) / configured_dir
    return configured_dir / getattr(settings, 'PERF_LOG_FILE', 'server_performance.log')


def _is_local_request(request):
    try:
        host = request.get_host().split(':', 1)[0].strip('[]').lower()
    except Exception:
        host = ''

    remote_addr = str(request.META.get('REMOTE_ADDR', '')).strip().lower()
    local_hosts = {'localhost', '127.0.0.1', '::1'}
    return host in local_hosts or remote_addr in local_hosts


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _viewer_token_query(request):
    token = request.GET.get('token', '').strip()
    return urlencode({'token': token}) if token else ''


def read_previous_log_lines(log_path, before=None, limit=LOG_PAGE_SIZE):
    path = Path(log_path)
    if not path.exists() or not path.is_file():
        return [], 0, False, 'Performance log file was not found.'

    try:
        file_size = path.stat().st_size
        end_at = file_size if before is None else max(0, min(int(before), file_size))
    except (OSError, TypeError, ValueError):
        return [], 0, False, 'Performance log file could not be inspected.'

    if end_at <= 0:
        return [], 0, False, None

    buffer = b''
    position = end_at
    bytes_read = 0

    try:
        with path.open('rb') as log_file:
            while position > 0 and bytes_read < MAX_TAIL_BYTES:
                chunk_size = min(READ_CHUNK_SIZE, position, MAX_TAIL_BYTES - bytes_read)
                position -= chunk_size
                log_file.seek(position)
                buffer = log_file.read(chunk_size) + buffer
                bytes_read += chunk_size

                parts = buffer.splitlines(keepends=True)
                usable_count = len(parts) - (1 if position > 0 and parts else 0)
                if usable_count >= limit:
                    break
    except OSError:
        return [], 0, False, 'Performance log file could not be read.'

    if not buffer:
        return [], 0, False, None

    parts = buffer.splitlines(keepends=True)
    skipped_prefix_bytes = 0
    if position > 0 and parts:
        skipped_prefix_bytes = len(parts[0])
        parts = parts[1:]

    selected = parts[-limit:]
    skipped_selected_bytes = sum(len(part) for part in parts[:-len(selected)]) if selected else 0
    next_before = position + skipped_prefix_bytes + skipped_selected_bytes
    has_more = next_before > 0

    lines = [
        part.decode('utf-8', errors='replace').strip()
        for part in selected
        if part.strip()
    ]
    return lines, next_before, has_more, None


def parse_log_lines(lines, selected_filter='all'):
    rows = []
    invalid_count = 0
    for original_index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            invalid_count += 1
            continue

        if is_viewer_self_request(event):
            continue

        metadata = event.get('metadata') if isinstance(event.get('metadata'), dict) else {}
        row = {
            'timestamp': _safe_display(event.get('timestamp')),
            'level': _safe_display(event.get('level')),
            'event_type': _safe_display(event.get('event_type')),
            'path': _safe_display(event.get('path')),
            'status_code': _safe_display(event.get('status_code')),
            'duration_ms': _safe_display(event.get('duration_ms')),
            'message': _safe_display(event.get('message')),
            'event_category': _safe_display(event.get('event_category')),
        }
        row['display_duration'] = display_duration(event, metadata)
        row['display_status'] = display_status(event, metadata)
        row['row_state'] = row_state(row)
        row['row_id'] = _row_id(line)
        row['_original_index'] = original_index
        if _matches_filter(row, selected_filter):
            rows.append(row)
    rows.sort(key=lambda item: item.get('timestamp') or '', reverse=True)
    for row in rows:
        row.pop('_original_index', None)
    return rows, invalid_count


def build_log_summary(lines):
    summary = {
        'server_status': 'Running',
        'total_loaded': 0,
        'slow_events': 0,
        'errors': 0,
        'db_events': 0,
        'image_events': 0,
        'report_events': 0,
        'login_events': 0,
    }
    invalid_count = 0
    for line in lines:
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            invalid_count += 1
            continue

        if is_viewer_self_request(event):
            continue

        event_type = str(event.get('event_type') or '').upper()
        category = str(event.get('event_category') or '').upper()
        level = str(event.get('level') or '').upper()
        path = str(event.get('path') or '').lower()
        metadata = event.get('metadata') if isinstance(event.get('metadata'), dict) else {}
        status = display_status(event, metadata)

        summary['total_loaded'] += 1
        if status == 'SLOW' or 'SLOW' in event_type:
            summary['slow_events'] += 1
        if level in {'ERROR', 'CRITICAL'} or status in {'ERROR', 'FAILED', 'INVALID'}:
            summary['errors'] += 1
        if category == 'DB':
            summary['db_events'] += 1
        if category == 'IMAGE':
            summary['image_events'] += 1
        if category == 'REPORT':
            summary['report_events'] += 1
        if event_type.startswith('AUTH.LOGIN'):
            summary['login_events'] += 1

    return summary, invalid_count


def is_viewer_self_request(event):
    path = str(event.get('path') or '').strip()
    return path.startswith(SELF_REQUEST_PATH)


def log_file_size_label(log_path):
    try:
        size = Path(log_path).stat().st_size
    except OSError:
        return 'Unavailable'

    units = ['B', 'KB', 'MB', 'GB']
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} {unit}'
        value /= 1024

    return 'Unavailable'


def display_duration(event, metadata=None):
    metadata = metadata or {}
    duration_keys = (
        ('event', 'duration_ms'),
        ('metadata', 'duration_ms'),
        ('metadata', 'total_db_time_ms'),
        ('metadata', 'query_duration_ms'),
        ('metadata', 'login_duration_ms'),
        ('metadata', 'response_duration_ms'),
        ('metadata', 'lookup_duration_ms'),
        ('metadata', 'generation_duration_ms'),
        ('metadata', 'download_duration_ms'),
    )
    for source, key in duration_keys:
        raw_value = event.get(key) if source == 'event' else metadata.get(key)
        value = _numeric_value(raw_value)
        if value is not None:
            return f'{value:.1f} ms'
    return '-'


def display_status(event, metadata=None):
    metadata = metadata or {}
    event_type = str(event.get('event_type') or '').upper()
    level = str(event.get('level') or '').upper()

    if event_type == 'REQUEST.END':
        return _safe_display(event.get('status_code')) or '-'
    if event_type == 'REQUEST.START':
        return 'STARTED'
    if event_type == 'REQUEST.SLOW':
        return 'SLOW'
    if event_type == 'ERROR.EXCEPTION':
        return 'ERROR'

    if event_type == 'AUTH.LOGIN.START':
        return 'STARTED'
    if event_type == 'AUTH.LOGIN.SUCCESS':
        return 'SUCCESS'
    if event_type == 'AUTH.LOGIN.FAILED':
        return 'FAILED'
    if event_type == 'AUTH.ACCOUNT_LOCKOUT.CHECK':
        return 'LOCKED' if _truthy(metadata.get('locked')) else 'OK'
    if event_type == 'AUTH.ACCOUNT_LOCKOUT.TRIGGERED':
        return 'LOCKED'
    if event_type == 'AUTH.SESSION.CREATED':
        return 'CREATED'
    if event_type == 'AUTH.SESSION.VALIDATED':
        return 'VALID'
    if event_type == 'AUTH.SESSION.EXPIRED':
        return 'EXPIRED'
    if event_type == 'AUTH.SESSION.INVALID':
        return 'INVALID'
    if event_type == 'AUTH.SINGLE_SESSION.CHECK':
        return 'STALE' if _truthy(metadata.get('stale')) else 'OK'

    if event_type == 'DB.REQUEST.START':
        return 'STARTED'
    if event_type in {'DB.REQUEST.END', 'DB.SUMMARY'}:
        return 'COMPLETED'
    if event_type == 'DB.QUERY.SLOW':
        return 'SLOW'
    if event_type == 'DB.CONNECTION.OPEN':
        return 'OPENED'
    if event_type == 'DB.CONNECTION.REUSED':
        return 'REUSED'

    if event_type == 'CACHE.HIT':
        return 'HIT'
    if event_type == 'CACHE.MISS':
        return 'MISS'
    if event_type == 'CACHE.SET':
        return 'SET'
    if event_type == 'CACHE.DELETE':
        return 'DELETED'

    if event_type == 'SERVICE.START':
        return 'STARTED'
    if event_type == 'SERVICE.END':
        return 'SUCCESS'
    if event_type == 'SERVICE.SLOW':
        return 'SLOW'
    if event_type == 'SERVICE.ERROR':
        return 'ERROR'

    if event_type == 'REPORT.START':
        return 'STARTED'
    if event_type == 'REPORT.END':
        return 'FAILED' if _falsey(metadata.get('success')) else 'SUCCESS'
    if event_type == 'REPORT.SLOW':
        return 'SLOW'
    if event_type == 'REPORT.ERROR':
        return 'ERROR'

    if event_type == 'IMAGE.LOOKUP.END':
        return 'FOUND' if _truthy(metadata.get('found')) else 'NOT_FOUND'
    if event_type == 'IMAGE.LOOKUP.NOT_FOUND':
        return 'NOT_FOUND'
    if event_type == 'IMAGE.SLOW':
        return 'SLOW'
    if event_type == 'IMAGE.ERROR':
        return 'ERROR'
    if event_type == 'IMAGE.MEDIA.WRITE':
        return 'WRITTEN'
    if event_type == 'IMAGE.MEDIA.DELETE':
        return 'DELETED'

    if event_type.startswith('STARTUP.'):
        return 'STARTUP'
    if event_type.startswith('SERVER.'):
        return 'OK'

    if event_type == 'THREAD.START':
        return 'STARTED'
    if event_type == 'THREAD.END':
        return 'COMPLETED'
    if event_type == 'THREAD.ERROR':
        return 'ERROR'
    if event_type == 'BACKGROUND.START':
        return 'STARTED'
    if event_type == 'BACKGROUND.END':
        return 'COMPLETED'
    if event_type == 'BACKGROUND.ERROR':
        return 'ERROR'

    if event_type == 'EXTERNAL.REQUEST.START':
        return 'STARTED'
    if event_type == 'EXTERNAL.REQUEST.END':
        return 'COMPLETED'
    if event_type == 'EXTERNAL.REQUEST.ERROR':
        return 'ERROR'

    if level in {'ERROR', 'CRITICAL'}:
        return 'ERROR'
    if 'SLOW' in event_type:
        return 'SLOW'
    if 'START' in event_type:
        return 'STARTED'
    if 'END' in event_type:
        return 'COMPLETED'
    return '-'


def row_state(row):
    level = row.get('level', '').upper()
    display = str(row.get('display_status') or '').upper()

    if level in {'ERROR', 'CRITICAL'} or display in {'ERROR', 'FAILED', 'INVALID', 'EXPIRED', 'LOCKED'}:
        return 'error'
    if display in {'SLOW', 'STALE'}:
        return 'slow'
    if display in {
        'SUCCESS',
        'OK',
        'COMPLETED',
        'VALID',
        'FOUND',
        'HIT',
        'CREATED',
        'OPENED',
        'REUSED',
        'WRITTEN',
        'DELETED',
        'SET',
    } or display.startswith('2') or display.startswith('3'):
        return 'success'
    return 'info'


def normalize_filter(value):
    return value if value in FILTERS else 'all'


def normalize_before(value):
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_display(value):
    if value is None:
        return ''
    text = str(value)
    return text[:180] + '...' if len(text) > 180 else text


def _numeric_value(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.lower().endswith('ms'):
        text = text[:-2].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _falsey(value):
    if isinstance(value, bool):
        return not value
    if value is None:
        return False
    return str(value).strip().lower() in {'0', 'false', 'no', 'off'}


def _row_id(line):
    return hashlib.sha256(str(line).encode('utf-8', errors='replace')).hexdigest()[:24]


def _matches_filter(row, selected_filter):
    if selected_filter == 'all':
        return True

    level = row.get('level', '').upper()
    event_type = row.get('event_type', '').upper()
    category = row.get('event_category', '').upper()
    path = row.get('path', '').lower()

    if selected_filter == 'errors':
        return level in {'ERROR', 'CRITICAL'} or 'ERROR' in event_type or 'EXCEPTION' in event_type
    if selected_filter == 'slow':
        return 'SLOW' in event_type
    if selected_filter == 'login':
        return event_type.startswith('AUTH.LOGIN') or '/accounts/login' in path
    if selected_filter == 'db':
        return category == 'DB' or event_type.startswith('DB.')
    if selected_filter == 'reports':
        return category == 'REPORT' or event_type.startswith('REPORT.') or 'reports' in path
    if selected_filter == 'images':
        return category == 'IMAGE' or event_type.startswith('IMAGE.')

    return True
