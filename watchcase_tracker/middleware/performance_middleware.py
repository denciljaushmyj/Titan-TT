import time

from django.db import connection

from watchcase_tracker.perf_logger import RequestPerf

# Prefixes to skip - static/media files don't need performance profiling.
_SKIP_PREFIXES = ('/static/', '/media/', '/favicon.ico')


class PerformanceProfilerMiddleware:
    """
    Breaks a request down into stages - MIDDLEWARE_AUTH, DB, VIEW (pure
    processing), TEMPLATE, plus any manual `time_stage(...)` blocks a view
    adds - and writes a per-stage breakdown to the 'performance' logger.

    Only requests that end up slow (see perf_logger.SLOW_REQUEST_MS) get a
    full breakdown logged; fast requests produce no output. DB time/count is
    measured with connection.execute_wrapper, which works with DEBUG=False
    (connection.queries does not) and keeps no query history in memory.

    Place this first in MIDDLEWARE so it wraps the entire chain (security,
    session, auth, view, etc.) and gives the widest possible measurement
    window.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES):
            return self.get_response(request)

        perf = RequestPerf(request.path)
        request._perf = perf

        def _db_wrapper(execute, sql, params, many, context):
            started = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                perf.record_db_query(time.perf_counter() - started)

        with connection.execute_wrapper(_db_wrapper):
            response = self.get_response(request)

        response_ready_at = time.perf_counter()
        perf.finalize(response_ready_at)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Called right before the view executes, after all other middleware's
        # request-side processing (security/session/auth) has already run -
        # marks the end of the combined MIDDLEWARE_AUTH stage.
        perf = getattr(request, '_perf', None)
        if perf is not None:
            perf.view_start = time.perf_counter()
        return None

    def process_template_response(self, request, response):
        # Only fires for TemplateResponse/SimpleTemplateResponse (e.g. DRF's
        # Response with TemplateHTMLRenderer). Actual rendering happens later
        # via response.render(), so timing is captured with a post-render
        # callback rather than here.
        perf = getattr(request, '_perf', None)
        if perf is not None:
            started = time.perf_counter()

            def _record(rendered_response):
                perf.record_template(time.perf_counter() - started)
                return rendered_response

            response.add_post_render_callback(_record)
        return response
