"""Sanitization helpers for performance log metadata."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence


MASK = "***MASKED***"
DEFAULT_MAX_VALUE_CHARS = 500
DEFAULT_MAX_KEY_CHARS = 120

SENSITIVE_KEY_PARTS = (
    "password",
    "old_password",
    "new_password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "bearer",
    "jwt",
    "csrf",
    "csrfmiddlewaretoken",
    "cookie",
    "cookies",
    "session",
    "sessionid",
    "session_id",
    "session_key",
    "authorization",
    "otp",
    "secret",
    "secret_key",
    "api_key",
    "apikey",
    "access_key",
    "refresh",
    "certificate",
    "pem",
    "connection_string",
    "database_url",
    "db_url",
    "db_uri",
    "dsn",
    "db_password",
    "private_key",
    "payload",
    "body",
    "raw_body",
    "request_body",
    "response_body",
    "file_content",
    "uploaded_file",
    "binary",
    "attachment",
)

SQL_KEY_PARTS = (
    "sql",
    "query",
    "statement",
    "command",
    "raw_sql",
    "where_clause",
)

SQL_LITERAL_RE = re.compile(
    r"('(?:''|[^'])*')|(\"(?:\"\"|[^\"])*\")|\b\d+(?:\.\d+)?\b"
)

SQL_TEXT_RE = re.compile(
    r"\b(SELECT|UPDATE|DELETE|INSERT|MERGE|WITH|FROM|WHERE|JOIN|VALUES|"
    r"ORDER\s+BY|GROUP\s+BY|HAVING|UNION|CREATE|ALTER|DROP)\b",
    re.IGNORECASE,
)


def is_sensitive_key(key) -> bool:
    try:
        lowered = str(key).lower()
    except Exception:
        return True
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def is_sql_key(key) -> bool:
    try:
        lowered = str(key).lower()
    except Exception:
        return False
    return any(part in lowered for part in SQL_KEY_PARTS)


def looks_like_sql(value) -> bool:
    try:
        return bool(SQL_TEXT_RE.search(str(value)))
    except Exception:
        return False


def truncate_value(value, max_chars=DEFAULT_MAX_VALUE_CHARS):
    try:
        text = str(value)
    except Exception:
        return "<unprintable>"
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...<truncated>"


def sanitize_sql(sql, max_chars=DEFAULT_MAX_VALUE_CHARS):
    try:
        text = str(sql)
        masked = SQL_LITERAL_RE.sub("?", text)
        digest = hashlib.sha256(masked.encode("utf-8", errors="ignore")).hexdigest()
        return f"sql:fingerprint:{digest[:24]}"
    except Exception:
        return "<sql-unavailable>"


def fingerprint_sql(sql) -> str:
    try:
        normalized = sanitize_sql(sql, max_chars=4000)
        digest = hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()
        return digest[:24]
    except Exception:
        return "unavailable"


def hash_value(value, prefix="sha256", length=16):
    try:
        digest = hashlib.sha256(str(value).encode("utf-8", errors="ignore")).hexdigest()
        return f"{prefix}:{digest[:length]}"
    except Exception:
        return f"{prefix}:unavailable"


def sanitize_headers(headers):
    return sanitize_metadata(dict(headers or {}))


def sanitize_metadata(value, max_chars=DEFAULT_MAX_VALUE_CHARS, _depth=0):
    try:
        if _depth > 5:
            return "<max-depth>"

        if value is None or isinstance(value, (bool, int, float)):
            return value

        if isinstance(value, bytes):
            return f"<bytes:{len(value)}>"

        if isinstance(value, str):
            if looks_like_sql(value):
                return sanitize_sql(value, max_chars=max_chars)
            return truncate_value(value, max_chars=max_chars)

        if isinstance(value, Mapping):
            sanitized = {}
            for key, item in value.items():
                safe_key = truncate_value(key, max_chars=DEFAULT_MAX_KEY_CHARS)
                if is_sql_key(safe_key) or looks_like_sql(item):
                    sanitized[safe_key] = sanitize_sql(item, max_chars=max_chars)
                    continue
                if is_sensitive_key(safe_key):
                    sanitized[safe_key] = MASK
                    continue
                sanitized[safe_key] = sanitize_metadata(
                    item,
                    max_chars=max_chars,
                    _depth=_depth + 1,
                )
            return sanitized

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [
                sanitize_metadata(item, max_chars=max_chars, _depth=_depth + 1)
                for item in list(value)[:50]
            ]

        return truncate_value(value, max_chars=max_chars)
    except Exception:
        return "<sanitize-error>"
