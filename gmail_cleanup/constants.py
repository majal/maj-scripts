"""Module-level constants, env-var names, and default path helpers shared
across gmail-cleanup.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
No behavior changes -- this module depends only on the standard library, so
it moved as the second, equally self-contained piece (see
gmail_cleanup/models.py for the first).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# Request the full tool scope set for every Gmail OAuth flow so cached tokens
# do not vary between report, dry-run, and apply commands.
APPLY_SCOPES = (
    READONLY_SCOPE,
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.insert",
)
DEFAULT_BACKUP_DIR_ENV = "GMAIL_CLEANUP_BACKUP_DIR"
DEFAULT_CONFIG_ENV = "GMAIL_CLEANUP_CONFIG"
DEFAULT_CREDENTIALS_ENV = "GMAIL_CLEANUP_OAUTH_CLIENT_SECRET"
DEFAULT_GMAIL_WEB_ACCOUNT = "0"
DEFAULT_GMAIL_WEB_ACCOUNT_ENV = "GMAIL_CLEANUP_GMAIL_WEB_ACCOUNT"
DEFAULT_GMAIL_USER_ENV = "GMAIL_CLEANUP_GMAIL_USER"
DEFAULT_MAX_RESULTS_ENV = "GMAIL_CLEANUP_MAX_RESULTS"
DEFAULT_PDF_MODE_ENV = "GMAIL_CLEANUP_PDF_MODE"
DEFAULT_PDF_ORIGINAL_ENV = "GMAIL_CLEANUP_PDF_ORIGINAL"
DEFAULT_PDF_PASSWORD_MODE_ENV = "GMAIL_CLEANUP_PDF_PASSWORD_MODE"
DEFAULT_PDF_PASSWORD_FAILURE_ACTION_ENV = "GMAIL_CLEANUP_PDF_PASSWORD_FAILURE_ACTION"
DEFAULT_PDF_PASSWORD_DATE_RANGE_ENV = "GMAIL_CLEANUP_PDF_PASSWORD_DATE_RANGE"
DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT_ENV = "GMAIL_CLEANUP_PDF_PASSWORD_FAMILY_FAIL_LIMIT"
DEFAULT_PDF_RENDER_DPI_ENV = "GMAIL_CLEANUP_PDF_RENDER_DPI"
DEFAULT_PDF_RENDER_FORMAT_ENV = "GMAIL_CLEANUP_PDF_RENDER_FORMAT"
DEFAULT_PDF_TEXT_MODE_ENV = "GMAIL_CLEANUP_PDF_TEXT_MODE"
DEFAULT_AUDIO_MODE_ENV = "GMAIL_CLEANUP_AUDIO_MODE"
DEFAULT_EMPTY_AFTER_REMOVAL_ENV = "GMAIL_CLEANUP_EMPTY_AFTER_REMOVAL"
DEFAULT_REQUEST_PROFILE_ENV = "GMAIL_CLEANUP_REQUEST_PROFILE"
DEFAULT_QUOTA_UNITS_PER_SECOND_ENV = "GMAIL_CLEANUP_QUOTA_UNITS_PER_SECOND"
DEFAULT_PROGRESS_FORMAT_ENV = "GMAIL_CLEANUP_PROGRESS_FORMAT"
DEFAULT_LABEL_PROCESSED_ENV = "GMAIL_CLEANUP_LABEL_PROCESSED"
DEFAULT_LABEL_REVIEW_ENV = "GMAIL_CLEANUP_LABEL_REVIEW"
DEFAULT_INDEX_DB_ENV = "GMAIL_CLEANUP_INDEX_DB"
DEFAULT_BEFORE_YEAR_ENV = "GMAIL_CLEANUP_BEFORE_YEAR"
DEFAULT_MIN_MESSAGE_BYTES_ENV = "GMAIL_CLEANUP_MIN_MESSAGE_BYTES"
DEFAULT_MIN_PART_BYTES_ENV = "GMAIL_CLEANUP_MIN_PART_BYTES"
DEFAULT_TOKEN_ENV = "GMAIL_CLEANUP_TOKEN_CACHE"
DEFAULT_TYPES_ENV = "GMAIL_CLEANUP_TYPES"
DEFAULT_EMBEDDED_IMAGE_DIR_ENV = "GMAIL_CLEANUP_EMBEDDED_IMAGE_DIR"
DEFAULT_SOFFICE_ENV = "GMAIL_CLEANUP_SOFFICE"
SKIPPED_LABEL_IDS = {"TRASH", "SPAM", "DRAFT"}
UNSUPPORTED_CONTENT_TYPES = {
    "multipart/signed",
    "application/pkcs7-mime",
    "application/pkcs7-signature",
    "application/pgp-encrypted",
    "application/pgp-signature",
}
STRIP_HEADERS = {
    "authentication-results",
    "delivered-to",
    "dkim-signature",
    "domainkey-signature",
    "message-id",
    "received",
    "received-spf",
    "return-path",
    "x-original-to",
    "x-received",
}
STRIP_HEADER_PREFIXES = ("arc-", "x-gm-", "x-google-")
EXTENSION_OVERRIDES = {
    "image/jpeg": ".jpg",
    "image/heic": ".heic",
    "video/quicktime": ".mov",
}
PDF_MIME_TYPE = "application/pdf"
GENERIC_ATTACHMENT_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/unknown",
}
VALID_ATTACHMENT_TYPES = (
    "image",
    "video",
    "pdf",
    "media",
    "large-media",
    "office",
    "archive",
    "audio",
    "legacy",
    "code",
    "calendar",
    "other",
)
VALID_PDF_MODES = ("auto", "render-pages", "extract-images", "backup")
VALID_PDF_ORIGINAL_RETENTION = ("keep", "trash", "discard")
VALID_PDF_PASSWORD_MODES = ("skip", "infer", "low-hanging")
VALID_PDF_PASSWORD_FAILURE_ACTIONS = ("skip", "trash-original")
VALID_PDF_RENDER_FORMATS = ("auto", "png", "jpg")
VALID_PDF_TEXT_MODES = ("none", "native", "ocr", "auto")
VALID_AUDIO_MODES = ("copy", "video", "video-plus-original")
VALID_EMPTY_AFTER_REMOVAL_MODES = ("skip", "note-only")
VALID_REQUEST_PROFILES = ("conservative", "moderate", "aggressive")
VALID_PROGRESS_FORMATS = ("text", "jsonl")
VALID_PRESETS = ("pdf-archive", "large-media", "office-docs", "archives", "audio-archive", "old-media")
LARGE_MEDIA_MIN_PART_BYTES = 1024 * 1024
OFFICE_ATTACHMENT_EXTENSIONS = {
    ".doc",
    ".docm",
    ".docx",
    ".dot",
    ".dotm",
    ".dotx",
    ".odp",
    ".ods",
    ".odt",
    ".pages",
    ".pps",
    ".ppsm",
    ".ppsx",
    ".ppt",
    ".pptm",
    ".pptx",
    ".pub",
    ".rtf",
    ".xls",
    ".xlsb",
    ".xlsm",
    ".xlsx",
}
ARCHIVE_ATTACHMENT_EXTENSIONS = {
    ".7z",
    ".bz2",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
}
AUDIO_ATTACHMENT_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".wav", ".wma"}
LEGACY_ATTACHMENT_EXTENSIONS = {
    ".bak",
    ".db",
    ".mdb",
    ".novabackup",
    ".sql",
}
CODE_ATTACHMENT_EXTENSIONS = {
    ".apk",
    ".bat",
    ".cmd",
    ".exe",
    ".jar",
    ".js",
    ".maj",
    ".msi",
    ".ps1",
    ".scr",
    ".vbs",
}
CALENDAR_ATTACHMENT_EXTENSIONS = {".ics"}
IGNORED_SIDECAR_EXTENSIONS = {".asc", ".sig"}
IGNORED_SIDECAR_MIME_TYPES = {
    "application/pgp-keys",
    "application/pgp-signature",
    "application/pkcs7-signature",
}
DEFAULT_PROCESSED_LABEL = "gmail-cleanup/processed"
DEFAULT_REVIEW_LABEL = "gmail-cleanup/review"
DEFAULT_PDF_RENDER_DPI = 300
DEFAULT_PDF_PASSWORD_DATE_RANGE = "1930-2035"
DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT = 3
PDF_DIRECT_IMAGE_GENERATIONS = {"pdf-extract", "pdf-render"}
PDF_PASSWORDED_ORIGINAL_TRASH_GENERATION = "pdf-passworded-original-trash"
PDF_UNREADABLE_ORIGINAL_TRASH_GENERATION = "pdf-unreadable-original-trash"
PDF_ORIGINAL_TRASH_GENERATIONS = {
    PDF_PASSWORDED_ORIGINAL_TRASH_GENERATION,
    PDF_UNREADABLE_ORIGINAL_TRASH_GENERATION,
}
PDF_NOTE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
EMBEDDED_IMAGE_EXTENSIONS = {".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
SOFFICE_EMBEDDED_IMAGE_TIMEOUT_SECONDS = 120
READABLE_BACKUP_SUBJECT_CHARS = 60
PASSWORD_HINT_PATTERN = re.compile(r"(?:password|passcode|pin)\s*(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9@._/-]{2,63})", re.IGNORECASE)
PASSWORD_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9@._/-]{3,63}")
NUMERIC_TOKEN_PATTERN = re.compile(r"\d{4,}")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
GMAIL_HTTP_TIMEOUT_SECONDS = 60
GMAIL_PUBLISHED_USER_QUOTA_UNITS_PER_SECOND = 250.0
REQUEST_PROFILE_CONFIG = {
    "conservative": {"batch_size": 5, "max_inflight": 1, "quota_units_per_second": 75.0},
    "moderate": {"batch_size": 10, "max_inflight": 1, "quota_units_per_second": 125.0},
    "aggressive": {"batch_size": 25, "max_inflight": 1, "quota_units_per_second": 175.0},
}
RETRYABLE_HTTP_STATUSES = {403, 429, 500, 502, 503, 504}
APPLY_PLAN_QUEUE_DEPTH = 50
PLAN_QUEUE_SENTINEL = object()
GMAIL_WRITE_MAX_ATTEMPTS = 4
GMAIL_WRITE_RETRY_BASE_SECONDS = 1.0
APPLY_QUEUE_VERSION = 1

RETRYABLE_GMAIL_REASONS = {
    "backendError",
    "rateLimitExceeded",
    "userRateLimitExceeded",
}
PDFCRACK_FOUND_PASSWORD_PATTERN = re.compile(r"found (?:user|owner)-password: '(?P<password>.*)'", re.IGNORECASE)
JOHN_SHOW_PASSWORD_PATTERN = re.compile(r"^(?P<label>[^:#\s][^:]*)[:](?P<password>[^:\n\r]*)", re.MULTILINE)
GMAIL_QUOTA_MESSAGES_LIST = 5
GMAIL_QUOTA_MESSAGES_GET = 5
GMAIL_QUOTA_MESSAGES_INSERT = 25
GMAIL_QUOTA_MESSAGES_MODIFY = 5
GMAIL_QUOTA_MESSAGES_TRASH = 5
GMAIL_QUOTA_THREADS_GET = 10
GMAIL_QUOTA_LABELS_LIST = 1
GMAIL_QUOTA_LABELS_CREATE = 5
PDF_ARCHIVE_PRESET_DEFAULTS = {
    "query": "filename:pdf -in:trash -in:spam",
    "max_results": 5000,
    "types": "pdf",
    "pdf_mode": "auto",
    "pdf_original": "trash",
    "pdf_password_mode": "low-hanging",
    "pdf_password_failure_action": "trash-original",
    "pdf_password_date_range": DEFAULT_PDF_PASSWORD_DATE_RANGE,
    "pdf_text_mode": "auto",
    "empty_after_removal": "note-only",
    "request_profile": "conservative",
    "quota_units_per_second": 80.0,
}
ATTACHMENT_CLEANUP_PRESET_DEFAULTS = {
    "pdf-archive": PDF_ARCHIVE_PRESET_DEFAULTS,
    "large-media": {
        "query": "has:attachment -in:trash -in:spam",
        "max_results": 50000,
        "types": "image,video",
        "min_message_bytes": 1000000,
        "request_profile": "conservative",
        "quota_units_per_second": 80.0,
    },
    "office-docs": {
        "query": "has:attachment -in:trash -in:spam",
        "max_results": 50000,
        "types": "office",
        "request_profile": "conservative",
        "quota_units_per_second": 80.0,
    },
    "archives": {
        "query": "has:attachment -in:trash -in:spam",
        "max_results": 50000,
        "types": "archive",
        "request_profile": "conservative",
        "quota_units_per_second": 80.0,
    },
    "audio-archive": {
        "query": "has:attachment -in:trash -in:spam",
        "max_results": 50000,
        "types": "audio",
        "audio_mode": "video",
        "request_profile": "conservative",
        "quota_units_per_second": 80.0,
    },
    "old-media": {
        "query": "has:attachment -in:trash -in:spam",
        "max_results": 50000,
        "types": "image,video",
        "before_year": 2018,
        "request_profile": "conservative",
        "quota_units_per_second": 80.0,
    },
}


def default_state_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "maj-scripts" / "gmail-cleanup"
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "maj-scripts" / "gmail-cleanup"
    return Path.home() / ".local" / "state" / "maj-scripts" / "gmail-cleanup"


def default_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "maj-scripts" / "gmail-cleanup" / "config.toml"
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "maj-scripts" / "gmail-cleanup" / "config.toml"
    return Path.home() / ".config" / "maj-scripts" / "gmail-cleanup" / "config.toml"


def legacy_state_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "maj-scripts" / "gmail_cleanup"
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "maj-scripts" / "gmail_cleanup"
    return Path.home() / ".local" / "state" / "maj-scripts" / "gmail_cleanup"


def legacy_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "maj-scripts" / "gmail_cleanup" / "config.toml"
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "maj-scripts" / "gmail_cleanup" / "config.toml"
    return Path.home() / ".config" / "maj-scripts" / "gmail_cleanup" / "config.toml"


DEFAULT_CONFIG_PATH = default_config_path()
LEGACY_CONFIG_PATH = legacy_config_path()
DEFAULT_TOKEN_PATH = default_state_dir() / "token.json"
LEGACY_TOKEN_PATH = legacy_state_dir() / "token.json"
DEFAULT_INDEX_DB_PATH = default_state_dir() / "gmail-index.sqlite"
PASSWORD_RECIPE_STORE_PATH = default_state_dir() / "pdf-password-recipes.json"
PASSWORD_SECRET_STORE_PATH = default_state_dir() / "pdf-password-secrets.json"
PASSWORD_FAILURE_STORE_PATH = default_state_dir() / "pdf-password-failures.json"
