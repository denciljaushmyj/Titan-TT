from django.contrib.auth import get_user_model
from modelmasterapp.models import SSOAccount
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

def link_sso_by_email_or_username(strategy, details, backend, uid, user=None, *args, **kwargs):
    """
    social-auth pipeline step:
    - If pipeline already resolved a user, ensure SSOAccount exists.
    - Otherwise try to find local user by provider email first, then by username (your 'names' like 'kauvery').
    - If found, attach SSOAccount and return {'user': user} so pipeline continues as authenticated.
    """
    email = (details.get('email') or '').strip()
    preferred_username = (details.get('username') or details.get('preferred_username') or details.get('name') or '').strip()
    response = kwargs.get('response') or {}

    logger.debug("SSO pipeline: backend=%s uid=%s email=%s username=%s", backend.name, uid, email, preferred_username)

    # If pipeline already resolved a user, ensure mapping exists
    if user:
        SSOAccount.objects.get_or_create(
            provider=backend.name,
            uid=uid,
            defaults={
                'user': user,
                'email': email,
                'name': details.get('fullname') or details.get('name'),
                'email_verified': details.get('email_verified', response.get('email_verified', False)),
                'extra_data': response,
            }
        )
        return {'user': user}

    # 1) Try mapping by email (preferred). Require email to exist.
    if email:
        qs = User.objects.filter(email__iexact=email)
        if qs.exists():
            user = qs.first()
            SSOAccount.objects.get_or_create(
                provider=backend.name,
                uid=uid,
                defaults={
                    'user': user,
                    'email': email,
                    'name': details.get('fullname') or details.get('name'),
                    'email_verified': details.get('email_verified', response.get('email_verified', False)),
                    'extra_data': response,
                }
            )
            logger.debug("Linked SSO by email to user=%s", user.username)
            return {'user': user}

    # 2) Fallback: try mapping by username (your names)
    if preferred_username:
        qs = User.objects.filter(username__iexact=preferred_username)
        if qs.exists():
            user = qs.first()
            SSOAccount.objects.get_or_create(
                provider=backend.name,
                uid=uid,
                defaults={
                    'user': user,
                    'email': email,
                    'name': details.get('fullname') or details.get('name'),
                    'email_verified': details.get('email_verified', response.get('email_verified', False)),
                    'extra_data': response,
                }
            )
            logger.debug("Linked SSO by username to user=%s", user.username)
            return {'user': user}

    # No match — let the rest of the pipeline create a new user (or stop per your policy)
    logger.debug("No existing user matched for SSO uid=%s; allowing pipeline to create user", uid)
    return {}