"""Data model types shared across gmail-cleanup: dataclasses, exceptions,
and small stateful helpers (rate pacing, progress reporting).

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
No behavior changes -- this module has no dependency on the rest of the
script, so it moved first as the safest, most self-contained piece.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class GmailMessageRecord:
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    raw_bytes: bytes
    history_id: str | None = None
    internal_date: int | None = None


@dataclass(frozen=True)
class SelectedMediaPart:
    path: tuple[int, ...]
    filename: str
    saved_filename: str
    search_token: str
    mime_type: str
    size_bytes: int
    disposition: str
    content_id: str | None


@dataclass(frozen=True)
class PlannedMessage:
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    subject: str
    sender: str
    date_header: str
    raw_bytes: bytes
    media_parts: tuple[SelectedMediaPart, ...]
    skip_reason: str | None = None


@dataclass
class InspectionState:
    planned: list[PlannedMessage] = field(default_factory=list)
    skipped: list[PlannedMessage] = field(default_factory=list)
    error: BaseException | None = None


@dataclass(frozen=True)
class BufferedMediaPart:
    path: tuple[int, ...]
    filename: str
    saved_filename: str
    search_token: str
    mime_type: str
    content_bytes: bytes
    disposition: str
    content_id: str | None


@dataclass(frozen=True)
class WrittenAttachment:
    local_path: Path
    filename: str
    original_filename: str
    search_token: str
    mime_type: str
    size_bytes: int
    sha256: str
    relative_path: str
    disposition: str
    content_id: str | None
    group_search_token: str | None = None
    source_attachment_mime_type: str | None = None
    source_generation: str | None = None
    source_page_number: int | None = None


@dataclass(frozen=True)
class PdfTextBlock:
    original_filename: str
    group_search_token: str
    text: str
    source: str


@dataclass(frozen=True)
class ExtractionSettings:
    attachment_types: tuple[str, ...]
    pdf_mode: str
    pdf_original: str
    pdf_password_mode: str
    pdf_password_failure_action: str
    pdf_password_date_range: tuple[int, int]
    pdf_password_family_fail_limit: int
    pdf_render_dpi: int
    pdf_render_format: str
    pdf_text_mode: str
    empty_after_removal: str
    audio_mode: str = "copy"
    before_year: int | None = None
    min_message_bytes: int = 0
    min_part_bytes: int = 0
    readable_folders: bool = False
    embedded_image_dir: Path | None = None
    soffice_path: str | None = None


@dataclass(frozen=True)
class AuditLabelSettings:
    processed: str | None = None
    review: str | None = None


@dataclass(frozen=True)
class ResolvedAuditLabels:
    processed_name: str | None = None
    processed_id: str | None = None
    review_name: str | None = None
    review_id: str | None = None


@dataclass(frozen=True)
class PasswordCandidate:
    value: str
    recipe: str


@dataclass(frozen=True)
class ResolvedPassword:
    value: str
    recipe: str
    backend: str


@dataclass(frozen=True)
class BatchFetchResult:
    chunk_index: int
    message_ids: tuple[str, ...]
    records: list[GmailMessageRecord]


class GmailRateLimitError(RuntimeError):
    """Raised when Gmail asks the client to slow down or reduce concurrency."""


class GmailTransientReadError(RuntimeError):
    """Raised when Gmail inspection fails with a retryable transport read error."""


class GmailQuotaPacer:
    def __init__(self, units_per_second: float) -> None:
        self.units_per_second = units_per_second
        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._next_available = 0.0

    def wait(self, units: float) -> None:
        if units <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_available - now)
            self._next_available = max(now, self._next_available) + (units / self.units_per_second)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def run(self, units: float, operation):
        with self._request_lock:
            self.wait(units)
            return operation()


class ProgressReporter:
    def __init__(self, verbose: int = 0, progress_format: str = "text") -> None:
        self.verbose = verbose
        self.progress_format = progress_format
        self._lock = threading.Lock()

    def log(self, level: int, message: str) -> None:
        if self.progress_format != "text" or self.verbose < level:
            return
        with self._lock:
            print(f"[gmail-cleanup] {message}", file=sys.stderr, flush=True)

    def event(self, event: str, **fields: object) -> None:
        if self.progress_format != "jsonl":
            return
        payload = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **fields,
        }
        with self._lock:
            print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)

    def log_event(self, level: int, message: str, event: str | None = None, **fields: object) -> None:
        self.log(level, message)
        if event is not None:
            self.event(event, **fields)


class SkippableMessageError(RuntimeError):
    """Raised when a message should be skipped without aborting the whole run."""
