from django.apps import AppConfig
from watchcase_tracker.performance_logging.startup import (
    duration_ms,
    emit_app_ready_end,
    emit_app_ready_start,
    emit_signals_registered,
    emit_startup_server_once,
    perf_counter,
)

class AdminportalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adminportal'

    def ready(self):
        emit_startup_server_once()
        ready_started = perf_counter()
        emit_app_ready_start()
        # Registers the user_logged_in / user_logged_out handlers that
        # enforce single-session-per-account behavior. Must be imported
        # here (not at module top-level) so Django's app registry is
        # fully ready before adminportal.signals imports adminportal.models.
        try:
            signals_started = perf_counter()
            import adminportal.signals  # noqa: F401
            signals_duration = duration_ms(signals_started)
            emit_signals_registered(signals_duration, success=True)
            emit_app_ready_end(duration_ms(ready_started), success=True)
        except Exception:
            emit_signals_registered(duration_ms(ready_started), success=False)
            emit_app_ready_end(duration_ms(ready_started), success=False)
            raise