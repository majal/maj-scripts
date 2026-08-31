"""Gmail API error classification and retry helpers for gmail-cleanup:
distinguishing retryable HTTP/transport errors from permanent failures, and
the retry-with-backoff wrapper used around Gmail write operations.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
Depends only on the standard library plus gmail_cleanup.constants (already
extracted), so it moved as the sixth self-contained piece. No behavior
changes.
"""

from __future__ import annotations

import http.client
import json
import random
import socket
import ssl
import time

from gmail_cleanup.constants import (
    GMAIL_WRITE_MAX_ATTEMPTS,
    GMAIL_WRITE_RETRY_BASE_SECONDS,
    RETRYABLE_GMAIL_REASONS,
    RETRYABLE_HTTP_STATUSES,
)


def http_error_status(exc: BaseException) -> int | None:
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    return None


def gmail_error_reason(exc: BaseException) -> str | None:
    content = getattr(exc, "content", None)
    if not content:
        return None
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    errors = payload.get("error", {}).get("errors", [])
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                reason = item.get("reason")
                if isinstance(reason, str):
                    return reason
    reason = payload.get("error", {}).get("status")
    return reason if isinstance(reason, str) else None


def is_retryable_gmail_request_error(exc: BaseException) -> bool:
    status = http_error_status(exc)
    if status in RETRYABLE_HTTP_STATUSES:
        return True
    reason = gmail_error_reason(exc)
    if reason in RETRYABLE_GMAIL_REASONS:
        return True
    message = str(exc).lower()
    return "too many concurrent requests for user" in message


def is_retryable_gmail_transport_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            BrokenPipeError,
            ConnectionError,
            ConnectionResetError,
            http.client.BadStatusLine,
            http.client.CannotSendRequest,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
        ),
    ):
        return True
    message = str(exc).lower()
    return any(
        fragment in message
        for fragment in (
            "broken pipe",
            "connection aborted",
            "connection reset",
            "eof occurred in violation of protocol",
            "nonetype' object has no attribute 'read'",
            "remote end closed connection without response",
            "temporarily unavailable",
            "timed out",
        )
    )


def is_invalid_scope_refresh_error(exc: BaseException) -> bool:
    return "invalid_scope" in str(exc)


def is_retryable_gmail_write_error(exc: BaseException) -> bool:
    return is_retryable_gmail_request_error(exc) or is_retryable_gmail_transport_error(exc)


def is_retryable_gmail_read_error(exc: BaseException) -> bool:
    return is_retryable_gmail_request_error(exc) or is_retryable_gmail_transport_error(exc)


def gmail_retry_delay(attempt: int) -> float:
    return min(30.0, GMAIL_WRITE_RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)) + random.random())


def execute_retryable_gmail_write(operation, *, action: str):
    last_error: BaseException | None = None
    for attempt in range(1, GMAIL_WRITE_MAX_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as exc:
            if not is_retryable_gmail_write_error(exc) or attempt == GMAIL_WRITE_MAX_ATTEMPTS:
                raise
            last_error = exc
            time.sleep(gmail_retry_delay(attempt))
    raise RuntimeError(f"Failed Gmail write action {action}") from last_error
