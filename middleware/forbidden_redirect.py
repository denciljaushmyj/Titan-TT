from django.shortcuts import redirect
from django.http import JsonResponse
from django.conf import settings

# API path prefixes that must never be redirected to login.
# For these paths, unauthenticated requests receive a JSON 401 response.
_API_PREFIXES = ('/adminportal/api/', '/api/')


class ForbiddenToLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _is_api_request(self, request):
        """Return True if the request targets an API endpoint."""
        if any(request.path.startswith(prefix) for prefix in _API_PREFIXES):
            return True
        # Also treat requests that explicitly accept JSON as API requests.
        accept = request.META.get('HTTP_ACCEPT', '')
        return 'application/json' in accept

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        is_authenticated = getattr(user, 'is_authenticated', False)

        if response.status_code in (401, 403) and not is_authenticated:
            if self._is_api_request(request):
                # For API requests, never redirect — return a plain JSON 401.
                return JsonResponse(
                    {'error': 'Authentication required.', 'code': 'NOT_AUTHENTICATED'},
                    status=401,
                )

            # For browser requests, redirect to the login page (original behaviour).
            if not request.path.startswith(settings.LOGIN_URL):
                return redirect(settings.LOGIN_URL + '?next=' + request.path)

        return response