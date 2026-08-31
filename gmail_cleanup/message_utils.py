"""Shared email/attachment parsing leaf helpers for gmail-cleanup: raw-bytes
to ``EmailMessage`` parsing, header lookup, filename sanitization/derivation,
MIME-type inference, attachment category classification, and byte-count
formatting.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
These functions live in a "genuinely tangled" region of the original script
(see docs/reports/2026-08-31-gmail-cleanup-modularity-split.md) full of
bidirectional call graphs, but each of the functions below is itself a pure
leaf -- it calls only the standard library, gmail_cleanup.constants, and
other functions in this same module, never back into the still-monolithic
parts of the script. They were pulled out as a prerequisite for extracting
the GmailIndex subsystem (gmail_cleanup.gmail_index), which needs several of
them (parse_email_message, header_value, human_size, message_filename_records,
and the attachment-classification helpers used by index analyze). Depends
only on the standard library plus gmail_cleanup.constants (already
extracted), so it moved as the tenth self-contained piece. No behavior
changes.
"""

from __future__ import annotations

import mimetypes
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from gmail_cleanup.constants import (
    ARCHIVE_ATTACHMENT_EXTENSIONS,
    AUDIO_ATTACHMENT_EXTENSIONS,
    CALENDAR_ATTACHMENT_EXTENSIONS,
    CODE_ATTACHMENT_EXTENSIONS,
    EXTENSION_OVERRIDES,
    GENERIC_ATTACHMENT_MIME_TYPES,
    IGNORED_SIDECAR_EXTENSIONS,
    IGNORED_SIDECAR_MIME_TYPES,
    LEGACY_ATTACHMENT_EXTENSIONS,
    OFFICE_ATTACHMENT_EXTENSIONS,
    PDF_MIME_TYPE,
)


def parse_email_message(raw_bytes: bytes) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(raw_bytes)


def header_value(message: EmailMessage, name: str) -> str:
    value = message.get(name, "")
    return str(value).strip()


def attachment_extension(filename: str | None) -> str:
    if not filename:
        return ""
    suffix = Path(filename).suffix.lower()
    return suffix if len(suffix) <= 24 else ""


def is_ignored_sidecar_part(part: EmailMessage) -> bool:
    return (
        attachment_extension(part.get_filename()) in IGNORED_SIDECAR_EXTENSIONS
        or part.get_content_type().lower() in IGNORED_SIDECAR_MIME_TYPES
    )


def infer_attachment_mime_type(part: EmailMessage) -> str:
    content_type = part.get_content_type().lower()
    filename = part.get_filename()
    guessed_type = mimetypes.guess_type(filename or "")[0]
    if guessed_type:
        guessed_type = guessed_type.lower()
    if guessed_type == PDF_MIME_TYPE:
        return PDF_MIME_TYPE
    if content_type in GENERIC_ATTACHMENT_MIME_TYPES and guessed_type:
        return guessed_type
    return content_type


def attachment_categories_for_part(part: EmailMessage) -> set[str]:
    content_type = infer_attachment_mime_type(part)
    maintype = content_type.split("/", 1)[0]
    extension = attachment_extension(part.get_filename())
    categories: set[str] = set()
    if is_ignored_sidecar_part(part):
        categories.add("ignored-sidecar")
        return categories
    if maintype == "image":
        categories.update(("image", "media"))
    if maintype == "video":
        categories.update(("video", "media"))
    if maintype == "audio" or extension in AUDIO_ATTACHMENT_EXTENSIONS:
        categories.add("audio")
    if content_type == PDF_MIME_TYPE or extension == ".pdf":
        categories.add("pdf")
    if extension in OFFICE_ATTACHMENT_EXTENSIONS or content_type in {
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.presentation",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.text",
        "application/rtf",
    }:
        categories.add("office")
    if extension in ARCHIVE_ATTACHMENT_EXTENSIONS or content_type in {
        "application/rar",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/x-tar",
        "application/x-zip-compressed",
        "application/zip",
    }:
        categories.add("archive")
    if extension in LEGACY_ATTACHMENT_EXTENSIONS:
        categories.add("legacy")
    if extension in CODE_ATTACHMENT_EXTENSIONS or content_type in {
        "application/javascript",
        "application/java-archive",
        "application/vnd.android.package-archive",
        "application/x-executable",
        "application/x-javascript",
        "text/javascript",
    }:
        categories.add("code")
    if extension in CALENDAR_ATTACHMENT_EXTENSIONS or content_type in {"application/ics", "text/calendar"}:
        categories.add("calendar")
    if not categories:
        categories.add("other")
    return categories


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    sanitized = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", base).strip(" .")
    return sanitized or "attachment"


def derive_attachment_filename(part: EmailMessage, index: int) -> str:
    filename = part.get_filename()
    if filename:
        return sanitize_filename(filename)
    ext = EXTENSION_OVERRIDES.get(part.get_content_type().lower()) or mimetypes.guess_extension(part.get_content_type()) or ""
    return f"part-{index:02d}{ext}"


def human_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def message_filename_records(message: EmailMessage) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        records.append(
            {
                "content_type": part.get_content_type().lower(),
                "disposition": part.get_content_disposition(),
                "filename": filename,
                "ignored_sidecar": is_ignored_sidecar_part(part),
            }
        )
    return records
