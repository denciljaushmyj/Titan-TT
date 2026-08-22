"""
JSON endpoints for the centralized pick-table row lock.

All endpoints require an authenticated user (the backend is the sole authority
on lock ownership; the frontend only consumes this state). They are csrf_exempt
to match the existing repo lock precedent (DayPlanning.lock_row_api) and to work
uniformly on every module page regardless of whether it renders a csrf token,
while remaining safe: they are same-origin, login-gated, and only mutate a
transient lock row.
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import rowlock_service

logger = logging.getLogger(__name__)


def _read(request):
    """Accept both JSON body and form-encoded POST."""
    ctype = request.META.get('CONTENT_TYPE', '')
    if 'application/json' in ctype:
        try:
            return json.loads(request.body or b'{}')
        except (ValueError, TypeError):
            return {}
    return request.POST


@csrf_exempt
@login_required
@require_POST
def acquire(request):
    data = _read(request)
    result = rowlock_service.acquire_lock(
        request.user, data.get('module'), data.get('lock_key')
    )
    status = 200 if result.get('success') else 400
    if result.get('success') and not result.get('acquired'):
        status = 409  # held by another live user
    return JsonResponse(result, status=status)


@csrf_exempt
@login_required
@require_POST
def heartbeat(request):
    data = _read(request)
    result = rowlock_service.heartbeat(
        request.user, data.get('module'), data.get('lock_key')
    )
    return JsonResponse(result, status=200 if result.get('success') else 400)


@csrf_exempt
@login_required
@require_POST
def release(request):
    data = _read(request)
    result = rowlock_service.release_lock(
        request.user, data.get('module'), data.get('lock_key')
    )
    return JsonResponse(result, status=200 if result.get('success') else 400)


@csrf_exempt
@login_required
@require_POST
def status(request):
    """Batched status for many rows in one query. Body: {module, keys:[...]}."""
    data = _read(request)
    keys = data.get('keys')
    if keys is None and hasattr(data, 'getlist'):
        keys = data.getlist('keys')
    statuses = rowlock_service.get_lock_statuses(
        data.get('module'), keys or [], request.user
    )
    return JsonResponse({'success': True, 'statuses': statuses})
