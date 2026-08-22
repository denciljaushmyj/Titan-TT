"""
Request-level performance profiling utilities.

Used by PerformanceProfilerMiddleware (watchcase_tracker/middleware/
performance_middleware.py) and by individual views/services that want to
time an expensive internal step (see `time_stage`).

Design notes:
- One RequestPerf instance is attached to `request._perf` for the lifetime
  of a single request. Nothing is stored outside of that per-request object,
  so there is no shared/global state and no query history kept in memory.
- DB timing uses `connection.execute_wrapper`, which works with DEBUG=False
  (unlike `connection.queries`, which is only populated when DEBUG=True).
- A full per-stage breakdown is only written to the 'performance' logger for
  requests that end up slow (>= SLOW_REQUEST_MS). Fast requests pay the
  (cheap) timing bookkeeping but produce no log output, so this does not add
  noise to production logs.
"""
import time
import uuid
import logging

logger = logging.getLogger('performance')

# Requests at/above this total duration get a full per-stage breakdown.
SLOW_REQUEST_MS = 1000


def new_request_id():
    return f"REQ-{uuid.uuid4().hex[:6].upper()}"


def _status(duration_ms):
    if duration_ms >= 5000:
        return 'CRITICAL'
    if duration_ms >= 1000:
        return 'SLOW'
    return 'OK'


class RequestPerf:
    """Per-request timing/DB accumulator. Lives on request._perf."""

    def __init__(self, path):
        self.request_id = new_request_id()
        self.path = path
        self.start = time.perf_counter()
        self.view_start = None
        self.db_time = 0.0
        self.db_count = 0
        self.template_time = 0.0
        self._manual_stages = []  # [(label, duration_seconds), ...]

    def record_db_query(self, duration_seconds):
        self.db_time += duration_seconds
        self.db_count += 1

    def record_template(self, duration_seconds):
        self.template_time += duration_seconds

    def record_manual_stage(self, label, duration_seconds):
        self._manual_stages.append((label, duration_seconds))

    def _emit(self, stage, duration_ms, db_queries=0, status=None):
        logger.info(
            "%s | %s | %s | %.0fms | %d | %s",
            self.request_id, self.path, stage, duration_ms, db_queries,
            status or _status(duration_ms),
        )

    def finalize(self, response_ready_at):
        """Called once by the middleware after the response is ready."""
        total_ms = (time.perf_counter() - self.start) * 1000
        status = _status(total_ms)
        if status == 'OK':
            return  # fast request - keep the log quiet

        middleware_ms = ((self.view_start - self.start) * 1000) if self.view_start else 0.0
        view_incl_db_ms = ((response_ready_at - self.view_start) * 1000) if self.view_start else 0.0
        db_ms = self.db_time * 1000
        template_ms = self.template_time * 1000
        # "Pure" view/python processing time = everything the view took minus
        # time already accounted for by DB waits and template rendering.
        view_pure_ms = max(view_incl_db_ms - db_ms - template_ms, 0.0)

        self._emit('MIDDLEWARE_AUTH', middleware_ms, 0)
        self._emit('DB', db_ms, self.db_count)
        self._emit('VIEW', view_pure_ms, self.db_count)
        for label, duration_s in self._manual_stages:
            self._emit(label, duration_s * 1000, 0)
        self._emit('TEMPLATE', template_ms, 0)
        self._emit('TOTAL', total_ms, self.db_count, status)


class time_stage:
    """Manual profiling context manager for an expensive internal function
    or service call. A no-op wrapper (the block still runs) if `request`
    wasn't handled by PerformanceProfilerMiddleware.

    Usage:
        with time_stage(request, 'DP_DATA_FETCH'):
            ...expensive code...
    """

    def __init__(self, request, label):
        self.perf = getattr(request, '_perf', None)
        self.label = label

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.perf is not None:
            self.perf.record_manual_stage(self.label, time.perf_counter() - self._start)
        return False
