import logging
import time

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .models import UserActiveSession
from watchcase_tracker.performance_logging.logger import emit_perf_event

logger = logging.getLogger(__name__)


def _emit_auth_event(request, event_type, level, message, metadata=None):
    try:
        emit_perf_event(
            'AUTH',
            event_type,
            level,
            message,
            metadata=metadata or {},
            request=request,
        )
    except Exception:
        return


def _get_client_ip(request):
    """Best-effort client IP, honoring a reverse proxy's X-Forwarded-For."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        ip = xff.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '') or ''

    # On IIS/some WSGI servers, REMOTE_ADDR includes the port ("1.2.3.4:5678").
    # GenericIPAddressField / PostgreSQL inet type rejects the port — strip it.
    # IPv4 with port has exactly one colon; IPv6 has multiple colons (safe to leave).
    if ip and ip.count(':') == 1:
        ip = ip.split(':')[0]

    return ip or None


def _get_login_source(request):
    """Best-effort classification of where the login originated."""
    path = request.path or ''
    if path.startswith('/admin/'):
        return 'django-admin'
    return 'web'


@receiver(user_logged_in)
def enforce_single_session_on_login(sender, request, user, **kwargs):
    """
    Single-session-per-account enforcement.

    On every successful login, if a different session is already recorded
    as active for this user, that old Django session row is deleted
    server-side (so that browser/device gets logged out on its next
    request), then UserActiveSession is updated to point at the new
    session.
    """
    if request is None:
        return

    signal_start = time.perf_counter()
    _emit_auth_event(
        request,
        'AUTH.SIGNAL.LOGIN',
        'INFO',
        'Login signal started',
        {
            'phase': 'start',
            'user_id': getattr(user, 'pk', None),
        },
    )
    session = getattr(request, 'session', None)
    new_session_key = getattr(session, 'session_key', None) if session else None
    if not new_session_key:
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGIN',
            'WARNING',
            'Login signal ended without session key',
            {
                'phase': 'end',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
                'created': False,
            },
        )
        return

    try:
        active_session = UserActiveSession.objects.filter(user=user).first()
        old_session_key = active_session.session_key if active_session else None
        replaced_existing_record = bool(old_session_key and old_session_key != new_session_key)

        if replaced_existing_record:
            Session.objects.filter(pk=old_session_key).delete()
            _emit_auth_event(
                request,
                'AUTH.SINGLE_SESSION.REPLACED',
                'WARNING',
                'Existing active record replaced',
                {
                    'user_id': getattr(user, 'pk', None),
                    'old_record_removed': True,
                },
            )

        _, created = UserActiveSession.objects.update_or_create(
            user=user,
            defaults={
                'session_key': new_session_key,
                'ip_address': _get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'login_source': _get_login_source(request),
            },
        )
        _emit_auth_event(
            request,
            'AUTH.SESSION.CREATED',
            'INFO',
            'Active session recorded',
            {
                'user_id': getattr(user, 'pk', None),
                'created': True,
                'active_record_created': created,
                'login_source': _get_login_source(request),
            },
        )
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGIN',
            'INFO',
            'Login signal completed',
            {
                'phase': 'end',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
                'created': True,
                'replaced_existing_record': replaced_existing_record,
            },
        )
    except Exception:
        # Session bookkeeping must never block a successful login.
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGIN',
            'ERROR',
            'Login signal failed',
            {
                'phase': 'error',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
            },
        )
        logger.exception(
            "Failed to enforce single-session-per-account for user_id=%s",
            getattr(user, 'pk', None),
        )


@receiver(user_logged_out)
def clear_active_session_on_logout(sender, request, user, **kwargs):
    """
    On logout, only clear UserActiveSession if it still matches the session
    that is logging out. This stops a stale/old browser tab's logout from
    wiping out a newer active session created by a more recent login
    elsewhere.
    """
    if request is None or user is None:
        return

    signal_start = time.perf_counter()
    _emit_auth_event(
        request,
        'AUTH.SIGNAL.LOGOUT',
        'INFO',
        'Logout signal started',
        {
            'phase': 'start',
            'user_id': getattr(user, 'pk', None),
        },
    )
    session = getattr(request, 'session', None)
    current_session_key = getattr(session, 'session_key', None) if session else None
    if not current_session_key:
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGOUT',
            'WARNING',
            'Logout signal ended without session key',
            {
                'phase': 'end',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
                'terminated': False,
            },
        )
        return

    try:
        deleted_count, _ = UserActiveSession.objects.filter(
            user=user, session_key=current_session_key
        ).delete()
        _emit_auth_event(
            request,
            'AUTH.LOGOUT',
            'INFO',
            'User logged out',
            {
                'user_id': getattr(user, 'pk', None),
                'terminated': bool(deleted_count),
                'logout_source': _get_login_source(request),
                'duration_seconds': None,
            },
        )
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGOUT',
            'INFO',
            'Logout signal completed',
            {
                'phase': 'end',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
                'terminated': bool(deleted_count),
            },
        )
    except Exception:
        _emit_auth_event(
            request,
            'AUTH.SIGNAL.LOGOUT',
            'ERROR',
            'Logout signal failed',
            {
                'phase': 'error',
                'user_id': getattr(user, 'pk', None),
                'duration_ms': round((time.perf_counter() - signal_start) * 1000, 3),
            },
        )
        logger.exception(
            "Failed to clear active session on logout for user_id=%s",
            getattr(user, 'pk', None),
        )
