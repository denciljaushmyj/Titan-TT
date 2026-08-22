import logging
import base64
import mimetypes
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger("security")

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
EMAIL_LOGO_STATIC_PATH = "assets/logo/titan_logo.png"

PENDING_MFA_USER_ID_KEY = "pending_mfa_user_id"
PENDING_MFA_OTP_HASH_KEY = "pending_mfa_otp_hash"
PENDING_MFA_EXPIRES_AT_KEY = "pending_mfa_expires_at"
PENDING_MFA_ATTEMPTS_KEY = "pending_mfa_attempts"
PENDING_MFA_LAST_SENT_AT_KEY = "pending_mfa_last_sent_at"
PENDING_MFA_OTP_VERSION_KEY = "pending_mfa_otp_version"


class MissingUserEmailError(ValueError):
    """Raised when an Email OTP cannot be sent because the user has no email."""


class OTPResendCooldownError(Exception):
    """Raised when a resend is requested before the cooldown has passed."""


def _get_email_logo_source():
    """
    Return the application logo source for email clients.

    Prefer a configured public URL. Otherwise embed the same static logo used
    by login and OTP pages as a data URI so no MIME attachment is created.
    """
    public_logo_url = getattr(settings, "EMAIL_LOGO_URL", "").strip()
    if public_logo_url.lower().startswith(("https://", "http://")):
        return public_logo_url

    logo_path = finders.find(EMAIL_LOGO_STATIC_PATH)
    if not logo_path:
        logger.warning("OTP_EMAIL_LOGO_NOT_FOUND: path=%s", EMAIL_LOGO_STATIC_PATH)
        return ""

    mime_type = mimetypes.guess_type(logo_path)[0] or "image/png"
    with open(logo_path, "rb") as logo_file:
        encoded_logo = base64.b64encode(logo_file.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded_logo}"


def generate_otp() -> str:
    """Return a cryptographically secure 6-digit numeric OTP."""
    otp = f"{secrets.randbelow(1_000_000):06d}"
    logger.info("OTP_GENERATED")
    if getattr(settings, "DEBUG", False):
        logger.info("OTP_GENERATED_DEBUG_SUFFIX: otp_last2=%s", otp[-2:])
    return otp


def hash_otp(otp: str) -> str:
    """Hash an OTP using Django's configured password hasher."""
    return make_password(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    """Verify a submitted OTP against its stored hash."""
    is_valid = check_password(otp, otp_hash)
    if is_valid:
        logger.info("OTP_VERIFIED")
    else:
        logger.warning("OTP_FAILED")
    return is_valid


def send_email_otp(user, otp: str) -> None:
    """Send the login OTP to the user's registered email address."""
    email = getattr(user, "email", "")
    if not email:
        logger.warning("OTP_SEND_FAILED_NO_EMAIL: user_id=%s", getattr(user, "id", None))
        raise MissingUserEmailError("User does not have an email address.")

    logo_src = _get_email_logo_source()
    html_message = render_to_string(
        "two_step_auth/login_otp_email.html",
        {
            "otp": otp,
            "user": user,
            "logo_src": logo_src,
        },
    )

    email_message = EmailMultiAlternatives(
        subject="Titan Track & Trace - Login Verification Code",
        body=(
            f"Your login verification code is: {otp}\n"
            "This code is valid for 5 minutes."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[email],
    )
    email_message.attach_alternative(html_message, "text/html")
    email_message.send(fail_silently=False)
    logger.info("OTP_SENT: user_id=%s", getattr(user, "id", None))


def _session_int(session, key: str, default: int = 0) -> int:
    try:
        return int(session.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def set_pending_otp_session(request, user, otp: str, reset_attempts: bool = True) -> int:
    """
    Store or replace the pending OTP challenge in the session.

    This is the single source of truth for pending OTP session mutation. Both
    initial OTP generation and resend must use this function.
    """
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    previous_version = _session_int(request.session, PENDING_MFA_OTP_VERSION_KEY, 0)
    version = previous_version + 1

    request.session[PENDING_MFA_USER_ID_KEY] = user.id
    request.session[PENDING_MFA_OTP_HASH_KEY] = hash_otp(otp)
    request.session[PENDING_MFA_EXPIRES_AT_KEY] = expires_at.isoformat()
    if reset_attempts:
        request.session[PENDING_MFA_ATTEMPTS_KEY] = 0
    request.session[PENDING_MFA_LAST_SENT_AT_KEY] = now.isoformat()
    request.session[PENDING_MFA_OTP_VERSION_KEY] = version
    request.session.modified = True

    logger.info(
        "OTP_SESSION_HASH_UPDATED: user_id=%s otp_version=%s",
        getattr(user, "id", None),
        version,
    )
    if getattr(settings, "DEBUG", False):
        logger.info(
            "OTP_GENERATED_DEBUG_SUFFIX: otp_version=%s otp_last2=%s",
            version,
            otp[-2:],
        )

    return version


def create_pending_otp_session(request, user) -> None:
    """
    Generate, email, and store a pending login OTP challenge in the session.

    The raw OTP is never stored in the session. Only the password-hashed OTP,
    expiry timestamp, attempt count, and last-send timestamp are persisted.
    """
    if not getattr(user, "email", ""):
        logger.warning("OTP_SESSION_NOT_CREATED_NO_EMAIL: user_id=%s", getattr(user, "id", None))
        raise MissingUserEmailError("User does not have an email address.")

    otp = generate_otp()
    request.session.pop(PENDING_MFA_OTP_VERSION_KEY, None)
    version = set_pending_otp_session(request, user, otp, reset_attempts=True)

    send_email_otp(user, otp)
    logger.info(
        "OTP_INITIAL_SESSION_SET: user_id=%s otp_version=%s",
        getattr(user, "id", None),
        version,
    )


def clear_pending_otp_session(request) -> None:
    """Remove all pending login OTP data from the session."""
    for key in (
        PENDING_MFA_USER_ID_KEY,
        PENDING_MFA_OTP_HASH_KEY,
        PENDING_MFA_EXPIRES_AT_KEY,
        PENDING_MFA_ATTEMPTS_KEY,
        PENDING_MFA_LAST_SENT_AT_KEY,
        PENDING_MFA_OTP_VERSION_KEY,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def validate_pending_otp_session(request, otp: str) -> Tuple[bool, str]:
    """
    Validate a submitted OTP against the pending session challenge.

    Returns:
        (True, "verified") when the OTP is valid.
        (False, reason) when the challenge is missing, expired, maxed out,
        or the OTP is invalid.
    """
    otp_hash = request.session.get(PENDING_MFA_OTP_HASH_KEY)
    expires_at = _parse_session_datetime(request.session.get(PENDING_MFA_EXPIRES_AT_KEY))
    attempts = int(request.session.get(PENDING_MFA_ATTEMPTS_KEY, 0))
    version = _session_int(request.session, PENDING_MFA_OTP_VERSION_KEY, 0)

    if not otp_hash or not expires_at:
        logger.info(
            "OTP_VERIFY_ATTEMPT: user_id=%s has_hash=%s expired=%s "
            "attempts=%s otp_version=%s check_password_result=%s reason=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
            bool(otp_hash),
            False,
            attempts,
            version,
            False,
            "missing",
        )
        return False, "missing"

    expired = timezone.now() > expires_at
    if expired:
        logger.info(
            "OTP_VERIFY_ATTEMPT: user_id=%s has_hash=%s expired=%s "
            "attempts=%s otp_version=%s check_password_result=%s reason=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
            bool(otp_hash),
            True,
            attempts,
            version,
            False,
            "expired",
        )
        logger.warning(
            "OTP_EXPIRED: user_id=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
        )
        clear_pending_otp_session(request)
        return False, "expired"

    if attempts >= OTP_MAX_ATTEMPTS:
        logger.info(
            "OTP_VERIFY_ATTEMPT: user_id=%s has_hash=%s expired=%s "
            "attempts=%s otp_version=%s check_password_result=%s reason=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
            bool(otp_hash),
            expired,
            attempts,
            version,
            False,
            "max_attempts",
        )
        logger.warning(
            "OTP_MAX_ATTEMPTS_REACHED: user_id=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
        )
        clear_pending_otp_session(request)
        return False, "max_attempts"

    if getattr(settings, "DEBUG", False):
        logger.info(
            "OTP_VERIFY_USING_CURRENT_HASH: user_id=%s has_hash=%s otp_version=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
            bool(otp_hash),
            version,
        )

    check_result = check_password(otp, otp_hash)
    logger.info(
        "OTP_VERIFY_ATTEMPT: user_id=%s has_hash=%s expired=%s "
        "attempts=%s otp_version=%s check_password_result=%s reason=%s",
        request.session.get(PENDING_MFA_USER_ID_KEY),
        bool(otp_hash),
        expired,
        attempts,
        version,
        check_result,
        "verified" if check_result else "invalid",
    )

    if check_result:
        logger.info("OTP_VERIFIED")
        return True, "verified"

    logger.warning("OTP_FAILED")
    new_attempts = attempts + 1
    request.session[PENDING_MFA_ATTEMPTS_KEY] = new_attempts
    request.session.modified = True

    if new_attempts >= OTP_MAX_ATTEMPTS:
        logger.warning(
            "OTP_MAX_ATTEMPTS_REACHED: user_id=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
        )
        clear_pending_otp_session(request)
        return False, "max_attempts"

    return False, "invalid"


def get_pending_otp_status(request):
    """Return safe diagnostic state for the current pending OTP session."""
    otp_hash = request.session.get(PENDING_MFA_OTP_HASH_KEY)
    expires_at = _parse_session_datetime(request.session.get(PENDING_MFA_EXPIRES_AT_KEY))
    attempts = int(request.session.get(PENDING_MFA_ATTEMPTS_KEY, 0))
    version = _session_int(request.session, PENDING_MFA_OTP_VERSION_KEY, 0)
    expired = bool(expires_at and timezone.now() > expires_at)

    return {
        "has_hash": bool(otp_hash),
        "expired": expired,
        "attempts": attempts,
        "otp_version": version,
    }


def get_resend_cooldown_remaining(request) -> int:
    """Return remaining OTP resend cooldown in seconds."""
    last_sent_at = _parse_session_datetime(request.session.get(PENDING_MFA_LAST_SENT_AT_KEY))
    if not last_sent_at:
        return 0

    elapsed = (timezone.now() - last_sent_at).total_seconds()
    remaining = OTP_RESEND_COOLDOWN_SECONDS - int(elapsed)
    return max(remaining, 0)


def can_resend_pending_otp(request) -> bool:
    """Return whether the pending OTP can be resent now."""
    return get_resend_cooldown_remaining(request) == 0


def resend_pending_otp_session(request, user) -> None:
    """
    Generate and send a replacement OTP for an existing pending challenge.

    On success, the old OTP hash is replaced, expiry is reset to 5 minutes,
    attempts are reset to 0, and last-send timestamp is updated.
    """
    if not can_resend_pending_otp(request):
        logger.warning(
            "OTP_RESEND_BLOCKED: user_id=%s",
            request.session.get(PENDING_MFA_USER_ID_KEY),
        )
        raise OTPResendCooldownError("OTP resend cooldown has not passed.")

    otp = generate_otp()
    version = set_pending_otp_session(request, user, otp, reset_attempts=True)

    try:
        send_email_otp(user, otp)
    except Exception:
        logger.exception("OTP_RESEND_FAILED: user_id=%s", getattr(user, "id", None))
        raise

    logger.info(
        "OTP_RESEND_NEW_HASH_SET: user_id=%s otp_version=%s",
        getattr(user, "id", None),
        version,
    )

    if getattr(settings, "DEBUG", False):
        logger.info(
            "OTP_RESENT: user_id=%s otp_version=%s otp_last2=%s",
            getattr(user, "id", None),
            version,
            otp[-2:],
        )
    else:
        logger.info(
            "OTP_RESENT: user_id=%s otp_version=%s",
            getattr(user, "id", None),
            version,
        )


def _parse_session_datetime(value: Optional[str]):
    if not value:
        return None

    parsed = parse_datetime(value)
    if parsed is None:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())

    return parsed
