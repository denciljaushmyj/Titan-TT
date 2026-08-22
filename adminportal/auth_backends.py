"""
Authentication backend enforcing the account lockout policy.

Security fix: Missing Account Lockout Policy.
Extends Django's ModelBackend so existing username/password authentication
behaviour is unchanged, except:
  - A locked account can never authenticate, even with the correct password.
  - Every failed password attempt for an existing user increments the
    consecutive-failure counter (account locks at the threshold).
  - A successful login resets the counter.

Enforcing this at the backend level covers every password-based login path:
the HTML login form (TimedLoginView), LoginAPIView, swap-login verification
and the Django admin login.
"""
import logging
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from watchcase_tracker.performance_logging.logger import emit_perf_event
from watchcase_tracker.performance_logging.sanitizer import hash_value

security_logger = logging.getLogger('security.auth')

def _perf_username(username):
    return hash_value((username or '').strip().lower()) if username else None


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


class AccountLockoutBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        check_start = time.perf_counter()
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        # Imported lazily to avoid app-registry issues at startup.
        from .services import (
            is_user_account_locked,
            record_failed_login_attempt,
            reset_failed_login_attempts,
        )

        target_user = UserModel.objects.filter(username=username).first()
        lockout_state = getattr(target_user, 'account_lockout', None) if target_user is not None else None

        if target_user is not None and is_user_account_locked(target_user):
            _emit_auth_event(
                request,
                'AUTH.ACCOUNT_LOCKOUT.CHECK',
                'WARNING',
                'Account lockout checked',
                {
                    'username_hash': _perf_username(username),
                    'user_id': getattr(target_user, 'pk', None),
                    'attempt_count': getattr(lockout_state, 'failed_attempts', None),
                    'locked': True,
                    'duration_ms': round((time.perf_counter() - check_start) * 1000, 3),
                },
            )
            security_logger.warning(
                'LOGIN_BLOCKED_LOCKED_ACCOUNT: user=%s ip=%s',
                username,
                request.META.get('REMOTE_ADDR', 'unknown') if request is not None else 'unknown',
            )
            # PermissionDenied makes django.contrib.auth.authenticate() fail
            # immediately without trying other backends or checking the password.
            raise PermissionDenied('Account is locked.')
        
        _emit_auth_event(
            request,
            'AUTH.ACCOUNT_LOCKOUT.CHECK',
            'INFO',
            'Account lockout checked',
            {
                'username_hash': _perf_username(username),
                'user_id': getattr(target_user, 'pk', None),
                'attempt_count': getattr(lockout_state, 'failed_attempts', None),
                'locked': False,
                'duration_ms': round((time.perf_counter() - check_start) * 1000, 3),
            },
        )

        user = super().authenticate(request, username=username, password=password, **kwargs)

        if user is not None:
            reset_failed_login_attempts(user)
        elif target_user is not None:
            lockout = record_failed_login_attempt(target_user, request=request)
            if getattr(lockout, 'is_locked', False):
                _emit_auth_event(
                    request,
                    'AUTH.ACCOUNT_LOCKOUT.TRIGGERED',
                    'WARNING',
                    'Account lockout triggered',
                    {
                        'username_hash': _perf_username(username),
                        'user_id': getattr(target_user, 'pk', None),
                        'attempt_count': getattr(lockout, 'failed_attempts', None),
                        'locked': True,
                    },
                )

        return user
