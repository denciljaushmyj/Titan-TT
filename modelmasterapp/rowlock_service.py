"""
Centralized pick-table row-lock service.

Single source of truth for acquiring, refreshing, releasing and inspecting
row locks used by every processing module. All ownership-changing operations
run inside transaction.atomic() with select_for_update() so concurrent
requests can never both win the same row (edge cases DP-001, IS-004,
SYS-002, SYS-008).

Locks self-expire via a heartbeat timestamp (no cron needed): a lock whose
heartbeat is older than PICK_ROW_LOCK_TTL_SECONDS is stale and may be
reclaimed, so browser close / refresh / crash never leaves a permanent lock.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PickRowLock

logger = logging.getLogger(__name__)

# Time a lock survives without a heartbeat before it is considered abandoned.
# Kept just above the frontend heartbeat interval (see row_lock_guard.js) so a
# live editor is never wrongly evicted, while an abandoned row frees quickly.
LOCK_TTL_SECONDS = getattr(settings, 'PICK_ROW_LOCK_TTL_SECONDS', 45)


def _display_name(user):
    full = (user.get_full_name() or '').strip()
    return full or user.get_username()


def _is_stale(lock, now=None):
    now = now or timezone.now()
    return (now - lock.heartbeat_at).total_seconds() > LOCK_TTL_SECONDS


def _payload(lock, current_user, acquired):
    """Build a backend-authoritative status payload for one lock row."""
    mine = lock.locked_by_id == current_user.id
    return {
        'success': True,
        'acquired': acquired,
        'locked': True,
        'mine': mine,
        'by': lock.locked_by_name or _display_name(lock.locked_by),
        'by_id': lock.locked_by_id,
    }


def acquire_lock(user, module, lock_key):
    """
    Try to acquire (or refresh) the lock for (module, lock_key).

    Returns a dict. `acquired` is True when the caller owns the row afterwards,
    False when another live user holds it. Safe under concurrent callers.
    """
    module = (module or '').strip()
    lock_key = (lock_key or '').strip()
    if not module or not lock_key:
        return {'success': False, 'error': 'module and lock_key are required.'}

    now = timezone.now()
    try:
        with transaction.atomic():
            lock = (
                PickRowLock.objects
                .select_for_update()
                .filter(module=module, lock_key=lock_key)
                .first()
            )

            if lock is None:
                # Create. A racing creator will hit the unique constraint below.
                lock = PickRowLock.objects.create(
                    module=module, lock_key=lock_key,
                    locked_by=user, locked_by_name=_display_name(user),
                    heartbeat_at=now,
                )
                return _payload(lock, user, acquired=True)

            owns = lock.locked_by_id == user.id
            if owns or _is_stale(lock, now):
                # Owner refresh, or reclaim of an abandoned (stale) lock.
                lock.locked_by = user
                lock.locked_by_name = _display_name(user)
                lock.heartbeat_at = now
                lock.save(update_fields=['locked_by', 'locked_by_name', 'heartbeat_at'])
                return _payload(lock, user, acquired=True)

            # Held by another live user.
            return _payload(lock, user, acquired=False)

    except IntegrityError:
        # Lost a create race: someone inserted the same (module, lock_key)
        # between our SELECT and INSERT. Re-read and report the winner.
        lock = PickRowLock.objects.filter(module=module, lock_key=lock_key).first()
        if lock is None:
            return {'success': False, 'error': 'Lock contention, please retry.'}
        return _payload(lock, user, acquired=(lock.locked_by_id == user.id))


def heartbeat(user, module, lock_key):
    """Keep the caller's lock alive. Re-acquires if it expired/was cleared."""
    return acquire_lock(user, module, lock_key)


def release_lock(user, module, lock_key):
    """Release the lock only if the caller owns it. No-op otherwise."""
    module = (module or '').strip()
    lock_key = (lock_key or '').strip()
    if not module or not lock_key:
        return {'success': False, 'error': 'module and lock_key are required.'}

    deleted, _ = PickRowLock.objects.filter(
        module=module, lock_key=lock_key, locked_by=user
    ).delete()
    return {'success': True, 'released': bool(deleted)}


def get_lock_statuses(module, lock_keys, current_user):
    """
    Batched, single-query status lookup for many rows (avoids N+1 polling).

    Returns {lock_key: {'by': name, 'by_id': id, 'mine': bool}} containing only
    rows currently held by a *live* lock. Stale locks are excluded (treated as
    free) so the caller does not have to know about expiry.
    """
    module = (module or '').strip()
    keys = [str(k).strip() for k in (lock_keys or []) if str(k).strip()]
    if not module or not keys:
        return {}

    now = timezone.now()
    statuses = {}
    rows = PickRowLock.objects.filter(module=module, lock_key__in=keys).only(
        'lock_key', 'locked_by_id', 'locked_by_name', 'heartbeat_at'
    )
    for lock in rows:
        if _is_stale(lock, now):
            continue
        statuses[lock.lock_key] = {
            'by': lock.locked_by_name,
            'by_id': lock.locked_by_id,
            'mine': lock.locked_by_id == current_user.id,
        }
    return statuses
