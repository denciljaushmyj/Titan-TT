"""Unified performance event emitter.

This module is intentionally infrastructure-only. It must not affect request,
authentication, database, media, report, or business behavior.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

from .sanitizer import sanitize_metadata, truncate_value


SCHEMA_VERSION = "1.0"
LOGGER_VERSION = "1.0"
LOGGER_NAME = "server_performance"
_STARTUP_EVENT_EMITTED = False
_STARTUP_EVENT_LOCK = threading.Lock()
_LOGGER = logging.getLogger(LOGGER_NAME)
_TZ_CACHE = {"name": None, "zone": None}

RESERVED_FIELDS = frozenset(
    {
        "schema_version",
        "logger_version",
        "timestamp",
        "level",
        "event_category",
        "event_type",
        "request_id",
        "correlation_id",
        "session_hash",
        "user_id",
        "authenticated",
        "module",
        "view",
        "service",
        "middleware",
        "thread_name",
        "thread_id",
        "process_id",
        "server_name",
        "environment",
        "path",
        "method",
        "status_code",
        "duration_ms",
        "message",
        "metadata",
    }
)


class PerformanceRotatingFileHandler(RotatingFileHandler):
    """Rotating handler that emits one safe startup-ready event."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._emit_logging_ready_record()

    def _emit_logging_ready_record(self):
        global _STARTUP_EVENT_EMITTED
        try:
            with _STARTUP_EVENT_LOCK:
                if _STARTUP_EVENT_EMITTED:
                    return
                _STARTUP_EVENT_EMITTED = True
            event = {
                "schema_version": SCHEMA_VERSION,
                "logger_version": LOGGER_VERSION,
                "timestamp": _timestamp(),
                "level": "INFO",
                "event_category": "STARTUP",
                "event_type": "STARTUP.LOGGING_READY",
                "process_id": os.getpid(),
                "thread_id": threading.get_ident(),
                "thread_name": truncate_value(threading.current_thread().name, max_chars=120),
                "environment": _environment(),
                "message": "Performance logging infrastructure is ready",
                "metadata": sanitize_metadata(
                    {
                        "logger_name": LOGGER_NAME,
                        "log_file": _setting("PERF_LOG_FILE", "server_performance.log"),
                        "mode": _setting("PERF_LOG_MODE", "basic"),
                    }
                ),
            }
            payload = json.dumps(event, ensure_ascii=True, separators=(",", ":"), default=str)
            record = logging.LogRecord(LOGGER_NAME, logging.INFO, __file__, 0, payload, (), None)
            self.emit(record)
        except Exception:
            return


def _setting(name, default=None):
    try:
        return getattr(settings, name, default)
    except Exception:
        return default


def _enabled() -> bool:
    return bool(_setting("PERF_LOG_ENABLED", False))


def _max_line_chars() -> int:
    try:
        return max(int(_setting("PERF_LOG_LINE_MAX_CHARS", 16000) or 16000), 1000)
    except Exception:
        return 16000


def _environment() -> str:
    try:
        cached = getattr(settings, "_perf_log_environment_cache", None)
        if cached:
            return cached
    except Exception:
        pass
    env = os.getenv("DJANGO_ENV") or os.getenv("ENVIRONMENT")
    if env:
        value = truncate_value(env, max_chars=80)
    else:
        value = "development" if bool(_setting("DEBUG", False)) else "production"
    try:
        setattr(settings, "_perf_log_environment_cache", value)
    except Exception:
        pass
    return value


def _timestamp() -> str:
    try:
        tz_name = _setting("TIME_ZONE", "UTC") or "UTC"
        if _TZ_CACHE["name"] != tz_name or _TZ_CACHE["zone"] is None:
            _TZ_CACHE["name"] = tz_name
            _TZ_CACHE["zone"] = ZoneInfo(tz_name)
        return datetime.now(_TZ_CACHE["zone"]).isoformat(timespec="milliseconds")
    except Exception:
        return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _mask_ip(value):
    try:
        if not value:
            return value
        text = str(value).strip()
        if "." in text:
            parts = text.split(".")
            if len(parts) == 4:
                return ".".join(parts[:3] + ["0"])
        if ":" in text:
            parts = text.split(":")
            return ":".join(parts[:4] + ["0000"])
        return text
    except Exception:
        return None


def _request_fields(request):
    if request is None:
        return {}

    try:
        user = getattr(request, "user", None)
        authenticated = bool(getattr(user, "is_authenticated", False))
        user_id = getattr(user, "id", None) if authenticated else None
        meta = getattr(request, "META", {}) or {}
        forwarded_for = meta.get("HTTP_X_FORWARDED_FOR", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else meta.get("REMOTE_ADDR")

        fields = {
            "request_id": getattr(request, "perf_request_id", None),
            "correlation_id": getattr(request, "perf_correlation_id", None),
            "path": getattr(request, "path", None),
            "method": getattr(request, "method", None),
            "authenticated": authenticated,
            "user_id": user_id,
            "client_ip": _mask_ip(client_ip),
            "x_forwarded_for": _mask_ip(forwarded_for.split(",")[0].strip()) if forwarded_for else None,
            "user_agent": meta.get("HTTP_USER_AGENT"),
            "request_size_bytes": meta.get("CONTENT_LENGTH") or None,
        }

        if bool(_setting("PERF_LOG_USERNAME_ENABLED", False)) and authenticated:
            fields["username"] = getattr(user, "get_username", lambda: None)()

        return sanitize_metadata(fields)
    except Exception:
        return {}


def emit_logging_ready():
    global _STARTUP_EVENT_EMITTED
    try:
        with _STARTUP_EVENT_LOCK:
            if _STARTUP_EVENT_EMITTED:
                return
            _STARTUP_EVENT_EMITTED = True
    except Exception:
        return

    emit_perf_event(
        "STARTUP",
        "STARTUP.LOGGING_READY",
        level="INFO",
        message="Performance logging infrastructure is ready",
        metadata={
            "logger_name": LOGGER_NAME,
            "log_file": _setting("PERF_LOG_FILE", "server_performance.log"),
            "mode": _setting("PERF_LOG_MODE", "basic"),
        },
        _skip_startup_event=True,
    )


def _emit_startup_once():
    emit_logging_ready()


def _safe_extra_fields(fields):
    try:
        if not fields:
            return {}
        safe_fields = {}
        ignored_reserved = []
        for key, value in fields.items():
            key_text = str(key)
            if key_text.lower() in RESERVED_FIELDS:
                ignored_reserved.append(key_text)
                continue
            safe_fields[key_text] = value
        metadata = {}
        if safe_fields:
            metadata["extra_fields"] = sanitize_metadata(safe_fields)
        if ignored_reserved:
            metadata["ignored_reserved_fields"] = sorted(set(ignored_reserved))
        return metadata
    except Exception:
        return {}


def _json_line(event):
    return json.dumps(event, ensure_ascii=True, separators=(",", ":"), default=str)


def _fit_json_line(event):
    try:
        max_chars = _max_line_chars()
        payload = _json_line(event)
        if len(payload) <= max_chars:
            return payload

        compact = dict(event)
        compact["metadata"] = {
            "truncated": True,
            "original_size_chars": len(payload),
        }
        payload = _json_line(compact)
        if len(payload) <= max_chars:
            return payload

        compact["message"] = truncate_value(compact.get("message", ""), max_chars=120)
        payload = _json_line(compact)
        if len(payload) <= max_chars:
            return payload

        minimal = {
            "schema_version": compact.get("schema_version", SCHEMA_VERSION),
            "logger_version": compact.get("logger_version", LOGGER_VERSION),
            "timestamp": compact.get("timestamp", _timestamp()),
            "level": compact.get("level", "INFO"),
            "event_category": compact.get("event_category", "SYSTEM"),
            "event_type": compact.get("event_type", "SYSTEM.TRUNCATED"),
            "process_id": compact.get("process_id", os.getpid()),
            "thread_id": compact.get("thread_id", threading.get_ident()),
            "thread_name": truncate_value(compact.get("thread_name", ""), max_chars=40),
            "environment": truncate_value(compact.get("environment", ""), max_chars=40),
            "message": "Performance log event truncated to fit line limit",
            "metadata": {
                "truncated": True,
                "original_size_chars": len(payload),
            },
        }
        payload = _json_line(minimal)
        while len(payload) > max_chars and minimal["metadata"]:
            minimal["metadata"] = {}
            payload = _json_line(minimal)
        return payload if len(payload) <= max_chars else ""
    except Exception:
        return ""


def emit_perf_event(
    event_category,
    event_type,
    level,
    message,
    metadata=None,
    request=None,
    _skip_startup_event=False,
    **fields,
):
    """Emit one sanitized JSON Lines performance event.

    All failures are swallowed by design. Diagnostic logging must never change
    application behavior.
    """
    try:
        if not _enabled():
            return

        if not _skip_startup_event:
            _emit_startup_once()

        level_name = str(level or "INFO").upper()
        if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            level_name = "INFO"

        thread = threading.current_thread()
        event = {
            "schema_version": SCHEMA_VERSION,
            "logger_version": LOGGER_VERSION,
            "timestamp": _timestamp(),
            "level": level_name,
            "event_category": truncate_value(event_category, max_chars=80),
            "event_type": truncate_value(event_type, max_chars=120),
            "process_id": os.getpid(),
            "thread_id": threading.get_ident(),
            "thread_name": truncate_value(thread.name, max_chars=120),
            "environment": _environment(),
            "message": truncate_value(message, max_chars=500),
            "metadata": sanitize_metadata(metadata or {}),
        }
        if not isinstance(event["metadata"], dict):
            event["metadata"] = {"value": event["metadata"]}
        event.update(_request_fields(request))
        extra_metadata = _safe_extra_fields(fields)
        if extra_metadata:
            event["metadata"]["caller_fields"] = extra_metadata

        payload = _fit_json_line(event)
        if not payload:
            return
        _LOGGER.log(
            getattr(logging, level_name, logging.INFO),
            payload,
        )
    except Exception:
        return
