import base64
from django.utils.crypto import get_random_string
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
import time
import logging

logger = logging.getLogger(__name__)


class BlockOptionsMiddleware:
    """
    Security middleware that rejects HTTP OPTIONS requests with 405 Method Not Allowed.

    Rationale:
    - This application has no CORS requirements (no django-cors-headers, no cross-origin
      consumers). OPTIONS preflight requests serve no functional purpose here.
    - Blocking OPTIONS globally prevents scanners and attackers from discovering
      supported HTTP methods and endpoint structure via OPTIONS introspection.
    - This middleware must be registered as the FIRST entry in MIDDLEWARE so that
      OPTIONS requests are rejected before any authentication, session, or CSRF
      processing occurs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS':
            response = HttpResponse(status=405)
            response['Allow'] = 'GET, POST, HEAD'
            response['Content-Length'] = '0'
            return response
        return self.get_response(request)

# ---------------------------------------------------------------------------
# URL-prefix → set of module names that grant access to that area.
# Any module name from USER_CATEGORY_MODULES that belongs to the group
# mapped to the prefix gives the user access.
# ---------------------------------------------------------------------------
_MODULE_URL_MAP = {
    'dayplanning/':               {'Data Upload', 'DP Pick Table', 'DP Complete Table'},
    'inputscreening/':            {'Input Pick Table', 'Input Completed Table', 'Input Accept Table', 'Input Reject Table', 'Input Screening'},
    'recovery_dp/':               {'Recovery Data Upload', 'Recovery Pick Table', 'Recovery Completed Table'},
    'recovery_is/':               {'R-Pick Table', 'R-Completed Table', 'R-Accept Table', 'R-Reject Table'},
    'recovery_brassqc/':          {'R-Brass Qc Pick Table', 'R-Brass Qc Completed Table'},
    'recovery_brass_audit/':      {'R-Brass Audit Pick Table', 'R-Brass Audit Reject Table', 'R-Brass Audit Complete Table'},
    'recovery_iqf/':              {'R-IQF Pick Table', 'R-IQF Accept Table', 'R-IQF Reject Table', 'R-IQF Completed Table'},
    'brass_qc/':                  {'Brass Qc Pick Table', 'Brass Qc Completed Table'},
    'brass_audit/':               {'Brass Audit Pick Table', 'Brass Audit Complete Table', 'Brass Audit Reject Table'},
    'iqf/':                       {'IQF Pick Table', 'IQF Completed Table', 'IQF Accept Table', 'IQF Reject Table'},
    'jig_loading/':               {'Jig Pick Table', 'Jig Completed Table'},
    'jig_unloading/':             {'JUL Main Table', 'JUL Completed'},
    'JigUnloading_Zone2/':        {'JUL Main Table Zone 2', 'JUL Completed Zone 2'},
    'inprocess_inspection/':      {'IP Main', 'IP Completed'},
    'nickle_inspection/':         {'Nickel Main Table', 'Nickel Completed Table'},
    'nickle_inspection_zone_two/': {'Nickel Inspection Zone 2 Pick Table', 'Nickel Inspection Zone 2 Completed Table', 'Nickel Inspection Zone 2 Reject Table'},
    'nickel_audit/':              {'NA Pick Table', 'NA Completed'},
    'nickel_audit_zone_two/':     {'Nickel Audit Zone 2 Pick Table', 'Nickel Audit Zone 2 Completed Table'},
    'spider_spindle/':            {'Spider Spindle Z1 Pick Table', 'Spider Spindle Z1 Completed Table'},
    'spider_spindle_zone_two/':   {'Spider Spindle Z2 Pick Table', 'Spider Spindle Z2 Completed Table'},
}

_MODULE_ACCESS_DENIED_MSG = 'Module cannot be accessible. Contact admin to get the access.'

_MODULE_ACCESS_DENIED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access Restricted</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #f1f5f9;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; }}
  .card {{ background: #fff; border-radius: 12px; padding: 3rem 2.5rem;
           max-width: 480px; width: 100%; text-align: center;
           box-shadow: 0 4px 24px rgba(0,0,0,0.10); }}
  .icon {{ font-size: 3.5rem; margin-bottom: 1rem; }}
  h1 {{ color: #dc2626; font-size: 1.4rem; margin-bottom: 0.5rem; }}
  p  {{ color: #475569; font-size: 1rem; margin-bottom: 1.5rem; }}
  a  {{ display: inline-block; background: #2563eb; color: #fff;
        padding: 0.6rem 1.5rem; border-radius: 6px; text-decoration: none;
        font-weight: 600; }}
  a:hover {{ background: #1d4ed8; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🔒</div>
  <h1>Access Restricted</h1>
  <p>{message}</p>
  <a href="/home/">Back to Dashboard</a>
</div>
</body>
</html>"""


class ModuleAccessMiddleware:
    """
    Intercepts requests to module URL prefixes and enforces that the
    authenticated user has at least one provisioned module for that area.

    - Unauthenticated users are passed through (login_required handles them).
    - Admin users are always allowed.
    - Non-HTML (API/JSON) requests receive a JSON 403.
    - HTML page requests receive a styled 403 page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lstrip('/')

        # Determine which module group this URL belongs to.
        required_modules = None
        for prefix, modules in _MODULE_URL_MAP.items():
            if path.startswith(prefix):
                required_modules = modules
                break

        if required_modules is None:
            # Not a module URL — skip.
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            # Not authenticated; let login_required redirect handle it.
            return self.get_response(request)

        # Lazy import to avoid circular imports at module load time.
        from adminportal.services import get_user_allowed_module_names, is_admin_user

        if is_admin_user(user):
            return self.get_response(request)

        allowed = set(get_user_allowed_module_names(user))
        if allowed.intersection(required_modules):
            return self.get_response(request)

        # Access denied.
        logger.warning(
            'MODULE_ACCESS_DENIED: user=%s path=%s required=%s',
            user.username,
            request.path,
            required_modules,
        )

        wants_json = (
            'application/json' in request.META.get('HTTP_ACCEPT', '')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.path.rstrip('/').split('/')[-1].startswith('api')
        )
        if wants_json:
            return JsonResponse({'error': _MODULE_ACCESS_DENIED_MSG}, status=403)

        html = _MODULE_ACCESS_DENIED_HTML.format(message=_MODULE_ACCESS_DENIED_MSG)
        return HttpResponse(html, status=403, content_type='text/html; charset=utf-8')

class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = base64.b64encode(get_random_string(16).encode()).decode()
        request.csp_nonce = nonce
        response = self.get_response(request)
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://unpkg.com https://cdn.jsdelivr.net/npm/sweetalert2@11 https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/;"
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://*.lottiefiles.com https://fonts.gstatic.com https://cdnjs.cloudflare.com https://demo.bootstrapdash.com;"
            "img-src 'self' https://assets2.lottiefiles.com/packages/lf20_uiyqFZ.json https://assets10.lottiefiles.com/packages/lf20_jcikwtux.json https://demo.bootstrapdash.com/skydash/themes/assets/images/logo-mini.svg https://demo.bootstrapdash.com/skydash/themes/assets/images/logo.svg https://demo.bootstrapdash.com/skydash/themes/assets/images/dashboard/people.svg data:; "
            "connect-src 'self' https://assets2.lottiefiles.com/packages/lf20_uiyqFZ.json https://assets10.lottiefiles.com/packages/lf20_jcikwtux.json https://www.google.com/recaptcha/;"
            "frame-src 'self' https://www.google.com/recaptcha/; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        return response


class LoginLatencyMiddleware:
    """
    Middleware to measure login flow latency.
    Logs timing for authentication, dashboard stats, and response rendering.
    Only active for login-related paths.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only profile login-related endpoints
        if request.path not in ('/', '/home/') and 'login' not in request.path and 'index' not in request.path:
            return self.get_response(request)

        request.start_time = time.time()
        request.timers = {}
        
        response = self.get_response(request)
        
        # Log total time
        total_time = (time.time() - request.start_time) * 1000  # Convert to ms
        
        timer_log = ' | '.join([f'{k}={v}' for k, v in request.timers.items()])
        if getattr(settings, 'ENABLE_LOGIN_LATENCY_LOGS', False):
            logger.warning(
                f'LOGIN_LATENCY: {request.path} | '
                f'Total={total_time:.2f}ms | {timer_log}'
            )
        
        # Add header with timing for debugging
        response['X-Login-Total-Time'] = f'{total_time:.2f}ms'
        for k, v in request.timers.items():
            response[f'X-Login-{k.upper()}'] = v
        
        return response


class SingleSessionMiddleware:
    """
    Security fix: Simultaneous Login / Concurrent Sessions.

    Enforces that a given user account can only have one valid (latest)
    session at a time. Works together with adminportal.signals (TASK 2),
    which writes/updates the user's current session key into
    adminportal.models.UserActiveSession on every successful login and
    clears it on logout.

    Placement requirement:
    Must be registered AFTER both
      - django.contrib.sessions.middleware.SessionMiddleware
      - django.contrib.auth.middleware.AuthenticationMiddleware
    in settings.MIDDLEWARE, so that request.session and request.user are
    already populated when this runs. It should also run before
    ModuleAccessMiddleware so stale sessions never reach module/business
    logic checks.

    Behavior:
    - Anonymous requests pass through untouched (login_required and the
      existing auth flow already handle them).
    - settings.LOGIN_URL, the logout URL, the Microsoft SSO entry points,
      Django Admin's own login/logout endpoints, and static/media paths are
      skipped so the in-flight authentication handshake (including SSO
      state validation) is never interrupted by this middleware.
    - For every other authenticated request, the current
      `request.session.session_key` is compared against the stored
      `UserActiveSession.session_key` for that user:
        * Missing session key, or no UserActiveSession row at all (e.g. a
          session that predates this feature, or whose record was
          removed): fails safe — the request is logged out and rejected.
          The next successful login recreates the row via the login
          signal.
        * Record exists and matches: request proceeds normally.
        * Record exists and does NOT match: the session is stale because a
          newer login happened elsewhere. The current request is logged
          out and rejected.
      Rejection returns JSON 401 for API/AJAX requests, or a redirect to
      settings.LOGIN_URL (with an informational message) for normal
      browser requests.
    - A failure while querying UserActiveSession (e.g. a transient DB
      error) is logged and the request is allowed through unenforced for
      that one request, rather than crashing or locking out the whole
      site.
    """

    _SKIP_PATH_PREFIXES = (
        '/static/',
        '/media/',
    )

    _SKIP_EXACT_PATHS = {
        '/accounts/profile/',
        '/auth/microsoft/login/',
        '/auth/microsoft/callback/',
    }

    _SKIP_PATH_STARTSWITH = (
        '/admin/login/',
        '/admin/logout/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_skip(request):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        current_session_key = getattr(request.session, 'session_key', None)
        if not current_session_key:
            logger.warning(
                'SINGLE_SESSION_NO_SESSION_KEY_REJECT: user=%s path=%s',
                user.username, request.path,
            )
            return self._reject(request)

        # Lazy import to avoid circular/app-registry import issues.
        from adminportal.models import UserActiveSession

        try:
            active_session = UserActiveSession.objects.filter(user=user).first()
        except Exception:
            # A DB hiccup here must never take the whole site down. Log
            # and let this one request through unenforced; the next
            # request will simply try the check again.
            logger.exception(
                'SINGLE_SESSION_LOOKUP_FAILED: user=%s path=%s',
                user.username, request.path,
            )
            return self.get_response(request)

        if active_session is None:
            # No record at all — fail safe by forcing re-authentication so
            # a fresh UserActiveSession row is created on the next login.
            logger.warning(
                'SINGLE_SESSION_NO_RECORD_REJECT: user=%s path=%s',
                user.username, request.path,
            )
            return self._reject(request)

        if active_session.session_key == current_session_key:
            return self.get_response(request)

        logger.warning(
            'SINGLE_SESSION_STALE_SESSION_REJECTED: user=%s path=%s '
            'request_session=%s active_session=%s',
            user.username, request.path, current_session_key, active_session.session_key,
        )
        return self._reject(request)

    def _login_url(self):
        return getattr(settings, 'LOGIN_URL', '/accounts/login/')

    def _logout_url(self):
        return getattr(settings, 'LOGOUT_URL', '/accounts/logout/')

    def _should_skip(self, request):
        path = request.path
        if path == self._login_url() or path == self._logout_url():
            return True
        if path in self._SKIP_EXACT_PATHS:
            return True
        for prefix in self._SKIP_PATH_PREFIXES:
            if path.startswith(prefix):
                return True
        for prefix in self._SKIP_PATH_STARTSWITH:
            if path.startswith(prefix):
                return True
        return False

    def _wants_json(self, request):
        return (
            'application/json' in request.META.get('HTTP_ACCEPT', '')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.path.startswith('/adminportal/api/')
        )

    def _reject(self, request):
        # Logs out the current (stale/invalid) request session. This also
        # fires user_logged_out, but the TASK 2 handler only clears
        # UserActiveSession if its stored session_key still matches the
        # session being logged out, so it safely no-ops here when the
        # active record already points at a newer session elsewhere.
        auth_logout(request)

        if self._wants_json(request):
            return JsonResponse(
                {'detail': 'Session expired because your account was logged in elsewhere.'},
                status=401,
            )

        try:
            messages.info(request, 'Your account was logged in from another location.')
        except Exception:
            # The messages framework may be unavailable/misconfigured;
            # never let that break the actual security enforcement.
            logger.debug('Could not attach single-session logout message.', exc_info=True)

        return redirect(self._login_url())


class EmailOTPMFARequiredMiddleware:
    """
    Enforces Email OTP completion for authenticated sessions.

    This middleware does not authenticate users and does not participate in
    password/CAPTCHA validation. It only checks already-authenticated requests
    and requires the session flag set by the Email OTP verification view:
    request.session["mfa_verified"] = True.
    """

    _SKIP_PATH_PREFIXES = (
        '/static/',
        '/media/',
    )

    _SKIP_EXACT_PATHS = {
        '/accounts/login/',
        '/accounts/logout/',
        '/accounts/verify-email-otp/',
        '/logout/',
        '/favicon.ico',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_skip(request):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        if request.session.get('mfa_verified') is True:
            logger.info(
                'MFA_VERIFIED_ALLOW: user=%s path=%s',
                getattr(user, 'username', 'unknown'),
                request.path,
            )
            return self.get_response(request)

        target = '/accounts/login/'
        if request.session.get('pending_mfa_user_id'):
            target = '/accounts/verify-email-otp/'

        logger.warning(
            'MFA_REQUIRED_REJECT: user=%s path=%s redirect=%s',
            getattr(user, 'username', 'unknown'),
            request.path,
            target,
        )
        return redirect(target)

    def _should_skip(self, request):
        path = request.path
        if path in self._SKIP_EXACT_PATHS:
            return True
        for prefix in self._SKIP_PATH_PREFIXES:
            if path.startswith(prefix):
                return True
        return False
