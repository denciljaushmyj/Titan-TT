import uuid
import logging
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseBadRequest
from urllib.parse import urlparse
import msal
import os

logger = logging.getLogger(__name__)


def _get_redirect_uri(request):
    """
    Build the OAuth redirect URI dynamically from the configured callback route.

    This keeps the redirect URI aligned with the registered Azure callback URL
    without hardcoding a path, and lets the app work correctly across local,
    dev-tunnel, and production hostnames.
    """
    base = settings.MSAL_REDIRECT_URI_BASE.strip().rstrip('/') if settings.MSAL_REDIRECT_URI_BASE else ""
    # The path must byte-for-byte match the URI registered in Azure (AADSTS50011
    # is raised on any mismatch, including a trailing slash). MSAL_REDIRECT_PATH
    # is the configured/registered form (env-overridable); reverse() is only a
    # fallback when the setting is not defined.
    path = (getattr(settings, 'MSAL_REDIRECT_PATH', '') or '').strip() or reverse('microsoft_callback')
    if not path.startswith('/'):
        path = f'/{path}'
    if base:
        return f"{base}{path}"
    return request.build_absolute_uri(path)


def _resolve_local_user_for_sso(email, preferred_name=''):
    """
    Find the local user that owns this SSO identity.

    STRICT matching by design: the Microsoft account's email/UPN must exactly
    equal a local user's email (or, for legacy accounts, the username that was
    stored as the full email address). No matching by display name or by the
    local part of the address — that could sign the person into someone
    else's (e.g. an admin's) account. If no exact match exists, the caller
    shows the "Contact Admin" message.
    """
    normalized_email = (email or '').strip().lower()
    if not normalized_email or '@' not in normalized_email:
        return None

    candidates = list(
        User.objects.filter(is_active=True)
        .filter(Q(email__iexact=normalized_email) | Q(username__iexact=normalized_email))
        .order_by('id')
    )
    if not candidates:
        return None

    # Duplicates (legacy data): prefer the account whose *email field* matches
    # over a username-only match, then the oldest. Never prefer by privilege.
    def rank(u):
        return (0 if (u.email or '').strip().lower() == normalized_email else 1, u.id)

    best = sorted(candidates, key=rank)[0]
    if len(candidates) > 1:
        logger.warning(
            "SSO email %s matched %d local accounts; using user_id=%s (%s). "
            "Please deduplicate in User Management.",
            normalized_email, len(candidates), best.id, best.username,
        )
    return best


def _provision_new_sso_user(email, name):
    """
    Create a minimal local account for a Microsoft identity that has no
    matching local user yet.

    No password is set (set_unusable_password via create_user's password=None),
    so this account can only ever sign in through SSO, never the
    username/password form. No modules are assigned, so
    adminportal.views.IndexView's existing "no modules assigned" check
    (show_sso_no_modules_alert) will show the "Access Restricted / Contact
    admin to access the portal" alert on the dashboard itself, and it
    auto-refreshes once an admin grants the account modules from User
    Management - instead of turning the person away at the login page before
    an admin has ever seen them.
    get_or_create (not create_user directly) guards against two concurrent
    first-time logins for the same brand-new email racing each other.
    """
    first_name, _, last_name = (name or '').strip().partition(' ')
    user, created = User.objects.get_or_create(
        username=email,
        defaults={'email': email, 'first_name': first_name, 'last_name': last_name},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
        logger.info("Auto-provisioned new local account for SSO identity %s (user_id=%s)", email, user.id)
    return user


def _get_authority():
    """Authority URL built from settings (env-driven), never hardcoded."""
    tenant = (getattr(settings, 'MSAL_TENANT_ID', '') or 'common').strip()
    return f"https://login.microsoftonline.com/{tenant}"


def microsoft_login(request):
    """Start the Microsoft OIDC Authorization Code flow by redirecting user."""
    if not settings.MSAL_CLIENT_ID or not settings.MSAL_CLIENT_SECRET:
        logger.error("MSAL client id/secret not configured in settings.")
        return redirect(f"{settings.LOGIN_URL}?sso_error=not_configured")

    # MSAL_REDIRECT_URI_BASE pins the origin Microsoft will send the browser
    # back to (it must byte-for-byte match what's registered in Azure). If
    # this page was reached on a different origin - e.g. http://127.0.0.1:8000
    # instead of http://localhost:8000 - the session set below would be
    # scoped to that other origin and never sent back once Microsoft
    # redirects to the fixed one, so the callback would see an empty session
    # and reject a completely legitimate login as "state mismatch". Bounce
    # once onto the configured origin before starting the flow so the
    # session that actually carries msal_states lives on the same origin
    # the callback will land on.
    configured_base = (settings.MSAL_REDIRECT_URI_BASE or '').strip()
    # Behind an IIS ARR/URL-Rewrite reverse proxy, request.get_host() reflects
    # whatever internal Host ARR forwards to the backend (e.g. 127.0.0.1:8000),
    # not the public hostname the browser/cookie actually use - so comparing
    # it to configured_netloc is meaningless there and only produced an
    # infinite self-redirect (ERR_TOO_MANY_REDIRECTS). SSO_SKIP_ORIGIN_BOUNCE
    # lets that deployment disable the bounce outright via env var; unset,
    # behavior for direct (non-proxied) hosting is unchanged.
    skip_bounce = os.getenv('SSO_SKIP_ORIGIN_BOUNCE', 'False').strip().lower() in ('1', 'true', 'yes', 'on')
    if configured_base and not skip_bounce and 'sso_bounced' not in request.GET:
        configured_netloc = urlparse(configured_base).netloc
        if configured_netloc and configured_netloc.lower() != request.get_host().lower():
            configured_scheme = urlparse(configured_base).scheme or request.scheme
            separator = '&' if '?' in request.get_full_path() else '?'
            target = f"{configured_scheme}://{configured_netloc}{request.get_full_path()}{separator}sso_bounced=1"
            logger.warning(
                "SSO login host mismatch: request host=%s configured=%s; bouncing once to %s",
                request.get_host(), configured_netloc, target,
            )
            return redirect(target)

    # Create and persist state to protect against CSRF. A small list of recent
    # states is kept (not a single value) because browsers may prefetch or the
    # user may double-click the sign-in link, issuing two login requests before
    # the callback returns; the callback consumes whichever state it matches.
    state = str(uuid.uuid4())
    pending_states = request.session.get('msal_states') or []
    pending_states = (pending_states + [state])[-5:]
    request.session['msal_states'] = pending_states
    request.session['msal_state'] = state  # kept for backward compatibility

    # MSAL performs network calls (OpenID configuration discovery) here.
    # If Microsoft's endpoints are unreachable (no internet/DNS/proxy), fail
    # gracefully back to the login page instead of raising a 500.
    try:
        authority = _get_authority()
        app = msal.ConfidentialClientApplication(
            client_id=settings.MSAL_CLIENT_ID,
            client_credential=settings.MSAL_CLIENT_SECRET,
            authority=authority,
        )

        redirect_uri = _get_redirect_uri(request)
        logger.debug("MSAL login redirect_uri=%s", redirect_uri)
        auth_url = app.get_authorization_request_url(
            scopes=settings.MSAL_SCOPES,
            state=state,
            redirect_uri=redirect_uri,
        )
        
        auth_url = (auth_url or "").strip()
        
        if auth_url.startswith("/"):
            auth_url = f"https://login.microsoftonline.com{auth_url}"
        
        parsed_auth_url = urlparse(auth_url)
        
        if (
            parsed_auth_url.scheme != "https"
            or parsed_auth_url.hostname != "login.microsoftonline.com"
        ):
            logger.error("Invalid Microsoft authorization URL generated: %r", auth_url)
            return redirect(f"{settings.LOGIN_URL}?sso_error=invalid_authority")
    except Exception:
        logger.exception("Microsoft SSO unreachable during login initiation.")
        return redirect(f"{settings.LOGIN_URL}?sso_error=unavailable")

    return redirect(auth_url)


def microsoft_callback(request):
    """Handle the redirect back from Microsoft and sign the user into Django."""
    error = request.GET.get('error')
    if error:
        desc = request.GET.get('error_description') or error
        logger.error("MSAL returned error: %s", desc)
        return HttpResponseBadRequest(f"Authentication error: {desc}")

    state = request.GET.get('state')
    session_state = request.session.get('msal_state')
    pending_states = request.session.get('msal_states') or ([session_state] if session_state else [])
    if not state or state not in pending_states:
        logger.warning("State mismatch in MSAL callback (session=%s, returned=%s)", pending_states, state)
        return HttpResponseBadRequest("State mismatch or missing. Potential CSRF detected.")
    # One-time use: consume the matched state so it cannot be replayed.
    request.session['msal_states'] = [s for s in pending_states if s != state]

    code = request.GET.get('code')
    if not code:
        logger.error("No authorization code received in callback.")
        return HttpResponseBadRequest("Authorization code not found in callback.")

    try:
        authority = _get_authority()
        app = msal.ConfidentialClientApplication(
            client_id=settings.MSAL_CLIENT_ID,
            client_credential=settings.MSAL_CLIENT_SECRET,
            authority=authority,
        )

        redirect_uri = _get_redirect_uri(request)
        result = app.acquire_token_by_authorization_code(
            code,
            scopes=settings.MSAL_SCOPES,
            redirect_uri=redirect_uri,
        )
    except Exception as e:
        logger.exception("Exception while acquiring token: %s", e)
        return redirect(f"{settings.LOGIN_URL}?sso_error=unavailable")

    if not result or 'error' in result:
        logger.error("Token acquisition failed: %s", result)
        return HttpResponseBadRequest("Token acquisition failed.")

    # ID token claims contain user info for OIDC
    id_token_claims = result.get('id_token_claims', {})
    email = id_token_claims.get('preferred_username') or id_token_claims.get('email') or id_token_claims.get('upn')
    name = id_token_claims.get('name') or ''

    if not email:
        logger.error("ID token did not contain an email/username claim: %s", id_token_claims)
        return HttpResponseBadRequest("Unable to determine user identity from ID token.")

    # Match by email/UPN first, then by username/local part and by name tokens.
    # A first-time Microsoft sign-in with no matching local user is no longer
    # turned away at the login page - it's auto-provisioned with no modules,
    # and the dashboard's existing "no modules assigned" alert
    # (show_sso_no_modules_alert, see the sso_just_logged_in flag below)
    # tells them to contact an admin, same wording as before, just after
    # login instead of before it.
    user = _resolve_local_user_for_sso(email, name)
    if user is None:
        user = _provision_new_sso_user(email, name)

    # Log the user in via Django session-based auth.
    # The backend MUST be one listed in settings.AUTHENTICATION_BACKENDS:
    # django.contrib.auth.get_user() drops the session (AnonymousUser) on the
    # next request if the stored backend path is not in that list, which sent
    # SSO users straight back to the login page.
    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

    # Parity with the username/password login flow (TimedLoginView.form_valid):
    # mark this session as MFA-verified so any MFA-enforcing middleware treats
    # SSO logins the same as form logins.
    request.session['mfa_verified'] = True
    # One-shot flag: lets the next page decide whether to show the
    # "no modules assigned" alert. Popped on read so it never reappears
    # on later navigation within the same session.
    request.session['sso_just_logged_in'] = True
    request.session.modified = True

    # Ensure the sidebar/dashboard reflect the latest admin-assigned module
    # provisions immediately (module names are cached per user).
    try:
        from adminportal.services import invalidate_user_modules_cache
        invalidate_user_modules_cache(user.id)
    except Exception:
        logger.debug("Could not invalidate module cache for user_id=%s", user.id)

    # Clean up pending states (one-time use)
    for key in ('msal_state', 'msal_states'):
        request.session.pop(key, None)

    # Redirect to dashboard / home
    return redirect(settings.LOGIN_REDIRECT_URL or '/home/')
