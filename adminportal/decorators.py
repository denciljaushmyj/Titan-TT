import logging
from functools import wraps
from django.http import JsonResponse
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

_ADMIN_403 = {
    'error': 'Access denied. Admin privileges required.',
    'code': 'ADMIN_REQUIRED',
}


def require_admin(view_func):
    """
    Restricts a view to authenticated admin users only.
    - Unauthenticated requests receive HTTP 401.
    - Authenticated non-admin requests receive HTTP 403 and the attempt is logged.
    - Role is fetched dynamically from the database via is_admin_user(); no
      usernames or role IDs are hardcoded.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .services import is_admin_user

        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return JsonResponse({'error': 'Authentication required.'}, status=401)

        if not is_admin_user(user):
            logger.warning(
                'UNAUTHORIZED_ADMIN_ACCESS: path=%s method=%s ip=%s',
                request.path,
                request.method,
                request.META.get('REMOTE_ADDR', 'unknown'),
            )
            return JsonResponse(_ADMIN_403, status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


class IsAdminPermission(BasePermission):
    """
    DRF permission class that restricts access to admin users only.
    Works with DEFAULT_PERMISSION_CLASSES = [IsAuthenticated] to produce:
      - 401 for unauthenticated requests (handled by IsAuthenticated first)
      - 403 for authenticated non-admin requests
    """
    message = 'Access denied. Admin privileges required.'

    def has_permission(self, request, view):
        from .services import is_admin_user

        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return False

        if not is_admin_user(request.user):
            logger.warning(
                'UNAUTHORIZED_ADMIN_ACCESS: path=%s method=%s ip=%s user=%s',
                request.path,
                request.method,
                request.META.get('REMOTE_ADDR', 'unknown'),
                request.user.username,
            )
            return False

        return True
