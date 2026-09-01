"""Marker-metadata embedding for gmail-cleanup: building the human-readable
"gmail-cleanup marker" text stamped into a written attachment's own
metadata tags (so the original Gmail message/thread can be found again from
the file alone), reading and merging existing exiftool/ffprobe tags rather
than clobbering them, and the two backend writers (exiftool for images/PDF/
QuickTime-family video, ffmpeg container metadata as a fallback) tied
together by ``embed_marker_metadata``.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md), which listed
this region ("metadata embedding... closely tied to WrittenAttachment
construction") as the fourth remaining monolithic cluster, not attempted
in the original pass for time/budget reasons rather than because it looked
unsafe. An AST-based call-graph trace of every function from
``metadata_marker_text`` through ``embed_marker_metadata`` found a clean
DAG rooted at ``embed_marker_metadata`` (no back-edges), and every external
name referenced resolves to the standard library or an already-extracted
module: gmail_cleanup.models (WrittenAttachment, PlannedMessage),
gmail_cleanup.naming (normalize_content_id, photos_search_query),
gmail_cleanup.tool_paths (resolve_exiftool_path/resolve_ffmpeg_path/
resolve_ffprobe_path), and gmail_cleanup.config (log_progress).

The four tag-name constants this cluster uses (IMAGE_METADATA_TAGS,
PDF_METADATA_TAGS, VIDEO_METADATA_TAGS, QUICKTIME_MIME_TYPES) were, at the
time of this extraction, still defined at top-level-script scope
immediately above the cluster rather than in gmail_cleanup/constants.py;
they were moved into constants.py as a small prerequisite step in this same
commit (verified via grep to have no other call sites), matching where
every other module-level constant already lives. No behavior changes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gmail_cleanup.config import log_progress
from gmail_cleanup.constants import (
    IMAGE_METADATA_TAGS,
    PDF_METADATA_TAGS,
    PDF_MIME_TYPE,
    PDF_ORIGINAL_TRASH_GENERATIONS,
    QUICKTIME_MIME_TYPES,
    VIDEO_METADATA_TAGS,
)
from gmail_cleanup.models import PlannedMessage, WrittenAttachment
from gmail_cleanup.naming import normalize_content_id, photos_search_query
from gmail_cleanup.tool_paths import resolve_exiftool_path, resolve_ffmpeg_path, resolve_ffprobe_path


def metadata_marker_text(
    attachment: WrittenAttachment,
    plan: PlannedMessage,
    operation_id: str,
    extracted_at: datetime,
) -> str:
    lines = [
        f"gmail-cleanup marker {attachment.search_token}",
        f'photos_search_query={photos_search_query(attachment.search_token)}',
        f"gmail_message_id={plan.message_id}",
        f"gmail_thread_id={plan.thread_id}",
        f"operation_id={operation_id}",
        f"saved_at={extracted_at.astimezone(timezone.utc).isoformat(timespec='seconds')}",
        f'original_filename="{attachment.original_filename}"',
        f'saved_filename="{attachment.filename}"',
        f'saved_relative_path="{attachment.relative_path}"',
        f"mime_type={attachment.mime_type}",
        f"size_bytes={attachment.size_bytes}",
        f"sha256={attachment.sha256}",
    ]
    if attachment.group_search_token and attachment.group_search_token != attachment.search_token:
        lines.append(f"group_search_token={attachment.group_search_token}")
        lines.append(f'group_photos_search_query={photos_search_query(attachment.group_search_token)}')
    if attachment.source_attachment_mime_type:
        lines.append(f"source_attachment_mime_type={attachment.source_attachment_mime_type}")
    if attachment.source_generation:
        lines.append(f"source_generation={attachment.source_generation}")
    if attachment.source_page_number is not None:
        lines.append(f"source_page_number={attachment.source_page_number}")
    if attachment.disposition:
        lines.append(f"disposition={attachment.disposition}")
    content_id = normalize_content_id(attachment.content_id)
    if content_id:
        lines.append(f"content_id={content_id}")
    return "\n".join(lines)


def metadata_tags_for_attachment(attachment: WrittenAttachment) -> tuple[str, ...]:
    if attachment.mime_type == PDF_MIME_TYPE:
        return PDF_METADATA_TAGS
    if attachment.mime_type.startswith("video/"):
        return VIDEO_METADATA_TAGS
    if not attachment.mime_type.startswith("image/"):
        return ("XMP-dc:Description", "XMP-dc:Subject")
    return IMAGE_METADATA_TAGS


def read_existing_metadata_tags(exiftool_path: str, attachment: WrittenAttachment) -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                exiftool_path,
                "-j",
                "-s",
                "-G1",
                *[f"-{tag}" for tag in metadata_tags_for_attachment(attachment)],
                str(attachment.local_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read existing metadata for {attachment.local_path}: {exc}") from exc
    if not payload:
        return {}
    return payload[0]


def merge_marker_value(existing: object, marker_text: str, search_token: str) -> str:
    if existing is None:
        return marker_text
    if isinstance(existing, list):
        existing_text = "\n".join(str(item) for item in existing if item is not None).strip()
    else:
        existing_text = str(existing).strip()
    if not existing_text:
        return marker_text
    if search_token in existing_text:
        return existing_text
    return f"{existing_text}\n\n{marker_text}"


def contains_subject_token(existing: object, search_token: str) -> bool:
    if existing is None:
        return False
    if isinstance(existing, list):
        return any(str(item).strip() == search_token for item in existing)
    return str(existing).strip() == search_token


def subject_tokens_for_attachment(attachment: WrittenAttachment) -> tuple[str, ...]:
    tokens = [attachment.search_token]
    if attachment.group_search_token and attachment.group_search_token != attachment.search_token:
        tokens.append(attachment.group_search_token)
    return tuple(tokens)


def build_exiftool_write_command(
    exiftool_path: str,
    attachment: WrittenAttachment,
    marker_text: str,
    existing_tags: dict[str, object],
) -> list[str]:
    command = [exiftool_path, "-overwrite_original", "-m", "-P"]
    if attachment.mime_type.startswith("image/"):
        command.extend(
            [
                f"-EXIF:UserComment={merge_marker_value(existing_tags.get('ExifIFD:UserComment'), marker_text, attachment.search_token)}",
                f"-EXIF:ImageDescription={merge_marker_value(existing_tags.get('IFD0:ImageDescription'), marker_text, attachment.search_token)}",
                f"-IPTC:Caption-Abstract={merge_marker_value(existing_tags.get('IPTC:Caption-Abstract'), marker_text, attachment.search_token)}",
            ]
        )
    if attachment.mime_type == PDF_MIME_TYPE:
        command.extend(
            [
                f"-PDF:Keywords={merge_marker_value(existing_tags.get('PDF:Keywords'), marker_text, attachment.search_token)}",
                f"-PDF:Subject={merge_marker_value(existing_tags.get('PDF:Subject'), marker_text, attachment.search_token)}",
            ]
        )
    if attachment.mime_type in QUICKTIME_MIME_TYPES:
        command.extend(
            [
                f"-ItemList:Comment={merge_marker_value(existing_tags.get('ItemList:Comment'), marker_text, attachment.search_token)}",
                f"-Keys:Description={merge_marker_value(existing_tags.get('Keys:Description'), marker_text, attachment.search_token)}",
            ]
        )
    command.append(f"-XMP-dc:Description={merge_marker_value(existing_tags.get('XMP-dc:Description'), marker_text, attachment.search_token)}")
    for token in subject_tokens_for_attachment(attachment):
        if not contains_subject_token(existing_tags.get("XMP-dc:Subject"), token):
            command.append(f"-XMP-dc:Subject+={token}")
    command.append(str(attachment.local_path))
    return command


def read_existing_ffprobe_tags(ffprobe_path: str, attachment: WrittenAttachment) -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format_tags",
                "-of",
                "json",
                str(attachment.local_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout or "{}")
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read existing ffprobe metadata for {attachment.local_path}: {exc}") from exc
    format_payload = payload.get("format")
    if not isinstance(format_payload, dict):
        return {}
    tags = format_payload.get("tags")
    if not isinstance(tags, dict):
        return {}
    return tags


def get_existing_ffprobe_tag(existing_tags: dict[str, object], name: str) -> object:
    target = name.casefold()
    for key, value in existing_tags.items():
        if key.casefold() == target:
            return value
    return None


def build_ffmpeg_metadata_write_command(
    ffmpeg_path: str,
    attachment: WrittenAttachment,
    marker_text: str,
    existing_tags: dict[str, object],
    output_path: Path,
) -> list[str]:
    return [
        ffmpeg_path,
        "-y",
        "-i",
        str(attachment.local_path),
        "-map",
        "0",
        "-map_metadata",
        "0",
        "-c",
        "copy",
        "-metadata",
        f"comment={merge_marker_value(get_existing_ffprobe_tag(existing_tags, 'comment'), marker_text, attachment.search_token)}",
        "-metadata",
        f"description={merge_marker_value(get_existing_ffprobe_tag(existing_tags, 'description'), marker_text, attachment.search_token)}",
        str(output_path),
    ]


def embed_marker_metadata_with_ffmpeg(attachment: WrittenAttachment, marker_text: str, *, assume_yes: bool = False) -> None:
    ffmpeg_path = resolve_ffmpeg_path(assume_yes=assume_yes)
    ffprobe_path = resolve_ffprobe_path(assume_yes=assume_yes)
    existing_tags = read_existing_ffprobe_tags(ffprobe_path, attachment)
    with tempfile.NamedTemporaryFile(
        prefix="gmail-cleanup-meta-",
        suffix=attachment.local_path.suffix,
        dir=attachment.local_path.parent,
        delete=False,
    ) as handle:
        output_path = Path(handle.name)
    try:
        command = build_ffmpeg_metadata_write_command(ffmpeg_path, attachment, marker_text, existing_tags, output_path)
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(f"Failed to embed marker metadata in {attachment.local_path} with ffmpeg: {detail}") from exc
        output_path.replace(attachment.local_path)
    finally:
        if output_path.exists():
            output_path.unlink()


def embed_marker_metadata_with_exiftool(
    exiftool_path: str,
    attachment: WrittenAttachment,
    marker_text: str,
) -> None:
    existing_tags = read_existing_metadata_tags(exiftool_path, attachment)
    command = build_exiftool_write_command(exiftool_path, attachment, marker_text, existing_tags)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to embed marker metadata in {attachment.local_path}: {detail}") from exc


def embed_marker_metadata(
    attachments: list[WrittenAttachment],
    plan: PlannedMessage,
    operation_id: str,
    extracted_at: datetime,
    verbose: int = 0,
    *,
    assume_yes: bool = False,
) -> None:
    exiftool_path = resolve_exiftool_path(assume_yes=assume_yes)
    for attachment in attachments:
        marker_text = metadata_marker_text(attachment, plan, operation_id, extracted_at)
        try:
            embed_marker_metadata_with_exiftool(exiftool_path, attachment, marker_text)
            log_progress(verbose, 3, f"Stamped metadata with exiftool for {attachment.filename}")
        except RuntimeError as exc:
            if attachment.source_generation in PDF_ORIGINAL_TRASH_GENERATIONS:
                log_progress(
                    verbose,
                    2,
                    f"Exiftool could not write metadata for original PDF {attachment.filename}; continuing before local Trash",
                )
                continue
            if attachment.mime_type.startswith("image/"):
                log_progress(
                    verbose,
                    2,
                    f"Exiftool could not write metadata for image {attachment.filename}; continuing with filename and manifest markers: {exc}",
                )
                continue
            if not attachment.mime_type.startswith("video/"):
                if attachment.mime_type != PDF_MIME_TYPE:
                    log_progress(
                        verbose,
                        2,
                        f"Exiftool could not write metadata for {attachment.filename}; continuing with filename and manifest markers",
                    )
                    continue
                raise
            log_progress(
                verbose,
                2,
                f"Exiftool could not write metadata for {attachment.filename}; falling back to ffmpeg container metadata",
            )
            embed_marker_metadata_with_ffmpeg(attachment, marker_text, assume_yes=assume_yes)
            log_progress(verbose, 3, f"Stamped metadata with ffmpeg for {attachment.filename}")
