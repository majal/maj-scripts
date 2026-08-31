"""Attachment/backup naming and destination-resolution leaf helpers for
gmail-cleanup: subject slugging, backup-folder and search-token naming,
saved-filename construction (top-level, PDF-page, embedded-image,
LibreOffice-embedded-image, and audio-video variants), CID normalization,
and on-disk destination resolution (collision-avoiding unique paths,
existing-file content matching, and MIME-sniff-driven filename/mime-type
correction for images).

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md). These functions
are physically interleaved with two regions that report calls "genuinely
tangled" -- email message parsing/collection (around ``collect_media_parts``)
and attachment writing (around ``write_bytes_attachment`` and friends) -- but
each function below is itself a pure leaf: it calls only the standard
library, ``gmail_cleanup.constants``, and ``gmail_cleanup.message_utils``
(specifically ``sanitize_filename``, already extracted), never back into the
still-monolithic writer/collector functions that surround it in the
original file. The doc's own "shared naming helpers" note
(``matching_destination``, ``build_saved_filename``, ``sanitize_filename``,
``attachment_extension``, referenced from 3+ places including the tangled
message-collection cluster) is resolved by this module together with the
prior ``message_utils`` extraction: ``sanitize_filename`` and
``attachment_extension`` were already pulled out; this module pulls out the
remaining two (and their own leaf dependents) so every caller -- tangled or
not -- imports from a shared leaf module instead of relying on file order.
Depends only on the standard library plus gmail_cleanup.constants and
gmail_cleanup.message_utils (both already extracted). No behavior changes.
"""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from pathlib import Path

from gmail_cleanup.constants import (
    EMBEDDED_IMAGE_EXTENSIONS,
    EXTENSION_OVERRIDES,
    READABLE_BACKUP_SUBJECT_CHARS,
)
from gmail_cleanup.message_utils import sanitize_filename
from gmail_cleanup.models import ExtractionSettings, PlannedMessage


def subject_slug(subject: str, max_chars: int = READABLE_BACKUP_SUBJECT_CHARS) -> str:
    normalized = unicodedata.normalize("NFKD", subject)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        return "no-subject"
    return slug[:max_chars].strip("-") or "no-subject"


def backup_folder_name_for_plan(plan: PlannedMessage, settings: ExtractionSettings) -> str:
    if not settings.readable_folders:
        return plan.message_id
    return sanitize_filename(f"{plan.message_id}__{subject_slug(plan.subject or '')}")


def build_search_token(message_id: str, ordinal: int) -> str:
    return f"gcm-{message_id}-{ordinal:02d}"


def build_saved_filename(search_token: str, original_filename: str) -> str:
    return sanitize_filename(f"{search_token}__{original_filename}")


def photos_search_query(search_token: str) -> str:
    return f'"{search_token}"'


def normalize_content_id(content_id: str | None) -> str | None:
    if content_id is None:
        return None
    normalized = content_id.strip()
    if normalized.lower().startswith("cid:"):
        normalized = normalized[4:]
    normalized = normalized.strip("<>")
    return normalized or None


def unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem or "attachment"
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}__{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_deterministic_backup_filename(filename: str) -> bool:
    return filename.startswith("gcm-")


def matching_destination(directory: Path, filename: str, content_bytes: bytes) -> Path:
    candidate = directory / filename
    if candidate.exists() and candidate.is_file():
        if is_deterministic_backup_filename(filename):
            return candidate
        try:
            if candidate.read_bytes() == content_bytes:
                return candidate
        except OSError:
            pass
    return unique_destination(directory, filename)


def guess_mime_type_from_filename(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed == "image/jpg":
        return "image/jpeg"
    return guessed or "application/octet-stream"


def sniff_image_mime_type(content_bytes: bytes) -> str | None:
    if content_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content_bytes.startswith(b"RIFF") and content_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def extension_for_mime_type(mime_type: str) -> str:
    return EXTENSION_OVERRIDES.get(mime_type) or mimetypes.guess_extension(mime_type) or ""


def normalize_image_destination(
    destination_name: str,
    mime_type: str,
    content_bytes: bytes,
) -> tuple[str, str]:
    actual_mime_type = sniff_image_mime_type(content_bytes)
    if actual_mime_type is None:
        return destination_name, mime_type
    if not (mime_type.startswith("image/") or guess_mime_type_from_filename(destination_name).startswith("image/")):
        return destination_name, mime_type
    actual_extension = extension_for_mime_type(actual_mime_type)
    if not actual_extension:
        return destination_name, actual_mime_type
    path = Path(destination_name)
    if path.suffix.lower() == actual_extension:
        return destination_name, actual_mime_type
    return sanitize_filename(f"{path.stem}{actual_extension}"), actual_mime_type


def build_pdf_page_search_token(base_search_token: str, page_number: int) -> str:
    return f"{base_search_token}-p{page_number:03d}"


def build_pdf_page_filename(search_token: str, original_filename: str, page_number: int, suffix: str) -> str:
    base = sanitize_filename(Path(original_filename).stem or "document")
    return sanitize_filename(f"{search_token}__{base}__page-{page_number:03d}{suffix}")


def build_embedded_image_filename(search_token: str, original_filename: str, member_name: str, image_index: int) -> str:
    original_stem = sanitize_filename(Path(original_filename).stem or "document")
    member_path = Path(member_name)
    member_stem = sanitize_filename(member_path.stem or "image")
    suffix = member_path.suffix.lower() if len(member_path.suffix) <= 12 else ""
    if suffix not in EMBEDDED_IMAGE_EXTENSIONS:
        suffix = ""
    return sanitize_filename(f"{search_token}-img{image_index:03d}__{original_stem}__{member_stem}{suffix}")


def build_libreoffice_embedded_image_filename(search_token: str, original_filename: str, output_name: str, image_index: int) -> str:
    original_stem = sanitize_filename(Path(original_filename).stem or "document")
    output_path = Path(output_name)
    output_stem = sanitize_filename(output_path.stem or "image")
    suffix = output_path.suffix.lower() if len(output_path.suffix) <= 12 else ""
    if suffix not in EMBEDDED_IMAGE_EXTENSIONS:
        suffix = ""
    return sanitize_filename(f"{search_token}-loimg{image_index:03d}__{original_stem}__{output_stem}{suffix}")


def build_audio_video_filename(search_token: str, original_filename: str) -> str:
    stem = sanitize_filename(Path(original_filename).stem or "audio")
    return build_saved_filename(search_token, f"{stem}__audio-video.mp4")
