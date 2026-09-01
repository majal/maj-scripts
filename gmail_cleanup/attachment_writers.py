"""Attachment-writing helpers for gmail-cleanup: writing extracted bytes/files
to the on-disk backup tree as ``WrittenAttachment`` records, embedded-image
extraction from Office documents (zip-based direct scan, LibreOffice
headless-conversion fallback), and audio-to-silent-video conversion so audio
attachments can be uploaded as Google Photos-visible media.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md). The report
flagged this region ("attachment writing", ``unique_destination`` through
``write_audio_video_attachment``) as sharing naming helpers referenced from
several places in the file. Tracing every call site showed those naming
helpers had no callers *inside* this cluster other than through the leaf
functions already pulled into ``gmail_cleanup.naming``, and -- separately --
that nothing in this cluster is called from, or calls into, the
message-parsing/note-injection cluster the report calls "genuinely tangled"
(``collect_media_parts`` through ``rewrite_message_for_backup``): a
region-by-region grep of both clusters' function names against each other
found zero cross-calls in either direction. This cluster's only callers are
the PDF/backup orchestration functions further down the file
(``write_pdf_outputs``, ``write_backup_files``), and its only internal
recursion is ``extract_embedded_images_from_document`` trying the zip-based
extractor before falling back to the LibreOffice one -- both defined in this
same module. Depends only on the standard library plus
gmail_cleanup.constants, gmail_cleanup.models, gmail_cleanup.message_utils,
gmail_cleanup.naming, gmail_cleanup.tool_paths, and gmail_cleanup.config
(all already extracted). No behavior changes.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from gmail_cleanup.config import log_progress
from gmail_cleanup.constants import (
    EMBEDDED_IMAGE_EXTENSIONS,
    OFFICE_ATTACHMENT_EXTENSIONS,
    SOFFICE_EMBEDDED_IMAGE_TIMEOUT_SECONDS,
)
from gmail_cleanup.message_utils import attachment_extension, sanitize_filename
from gmail_cleanup.models import BufferedMediaPart, WrittenAttachment
from gmail_cleanup.naming import (
    build_audio_video_filename,
    build_embedded_image_filename,
    build_libreoffice_embedded_image_filename,
    guess_mime_type_from_filename,
    matching_destination,
    normalize_image_destination,
    sniff_image_mime_type,
)
from gmail_cleanup.tool_paths import resolve_ffmpeg_path


def write_bytes_attachment(
    backup_dir: Path,
    message_dir: Path,
    *,
    destination_name: str,
    original_filename: str,
    search_token: str,
    mime_type: str,
    content_bytes: bytes,
    disposition: str,
    content_id: str | None,
    group_search_token: str | None = None,
    source_attachment_mime_type: str | None = None,
    source_generation: str | None = None,
    source_page_number: int | None = None,
) -> WrittenAttachment:
    destination_name, mime_type = normalize_image_destination(destination_name, mime_type, content_bytes)
    destination = matching_destination(message_dir, destination_name, content_bytes)
    if not destination.exists():
        destination.write_bytes(content_bytes)
    relative_path = destination.relative_to(backup_dir).as_posix()
    return WrittenAttachment(
        local_path=destination,
        filename=destination.name,
        original_filename=original_filename,
        search_token=search_token,
        mime_type=mime_type,
        size_bytes=len(content_bytes),
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        relative_path=relative_path,
        disposition=disposition,
        content_id=content_id,
        group_search_token=group_search_token,
        source_attachment_mime_type=source_attachment_mime_type or mime_type,
        source_generation=source_generation,
        source_page_number=source_page_number,
    )


def find_soffice_executable(configured: str | None = None) -> str | None:
    candidates = (configured,) if configured else ("soffice", "libreoffice")
    for candidate in candidates:
        if candidate is None:
            continue
        expanded = os.path.expanduser(candidate.strip())
        if not expanded:
            continue
        if os.sep in expanded or (os.altsep is not None and os.altsep in expanded):
            path = Path(expanded)
            if path.is_file():
                return str(path)
            continue
        resolved = shutil.which(expanded)
        if resolved:
            return resolved
    return None


def extract_zip_embedded_images_from_document(
    media_part: BufferedMediaPart,
    embedded_image_dir: Path | None,
    backup_folder_name: str,
    *,
    verbose: int = 0,
) -> list[WrittenAttachment]:
    if embedded_image_dir is None:
        return []
    extension = attachment_extension(media_part.filename)
    if extension not in OFFICE_ATTACHMENT_EXTENSIONS:
        return []
    try:
        archive = zipfile.ZipFile(io.BytesIO(media_part.content_bytes))
    except zipfile.BadZipFile:
        log_progress(verbose, 3, f"No zip-based embedded image scan for {media_part.filename}")
        return []
    written: list[WrittenAttachment] = []
    media_dir = embedded_image_dir / backup_folder_name
    with archive:
        image_index = 0
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_name = member.filename
            suffix = Path(member_name).suffix.lower()
            if suffix not in EMBEDDED_IMAGE_EXTENSIONS:
                continue
            image_bytes = archive.read(member)
            if not image_bytes:
                continue
            image_index += 1
            media_dir.mkdir(parents=True, exist_ok=True)
            image_token = f"{media_part.search_token}-img{image_index:03d}"
            written.append(
                write_bytes_attachment(
                    embedded_image_dir,
                    media_dir,
                    destination_name=build_embedded_image_filename(media_part.search_token, media_part.filename, member_name, image_index),
                    original_filename=f"{media_part.filename}:{member_name}",
                    search_token=image_token,
                    mime_type=guess_mime_type_from_filename(member_name),
                    content_bytes=image_bytes,
                    disposition="derived",
                    content_id=None,
                    group_search_token=media_part.search_token,
                    source_attachment_mime_type=media_part.mime_type,
                    source_generation="embedded-image",
                )
            )
    if written:
        log_progress(verbose, 2, f"Extracted {len(written)} embedded image(s) from {media_part.filename}")
    return written


def extract_libreoffice_embedded_images_from_document(
    media_part: BufferedMediaPart,
    embedded_image_dir: Path | None,
    backup_folder_name: str,
    *,
    soffice_path: str | None = None,
    verbose: int = 0,
) -> list[WrittenAttachment]:
    if embedded_image_dir is None:
        return []
    extension = attachment_extension(media_part.filename)
    if extension not in OFFICE_ATTACHMENT_EXTENSIONS:
        return []
    soffice = find_soffice_executable(soffice_path)
    if soffice is None:
        log_progress(verbose, 2, f"LibreOffice not available for embedded image scan of {media_part.filename}")
        return []
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-soffice-") as temp_name:
        temp_dir = Path(temp_name)
        input_dir = temp_dir / "input"
        output_dir = temp_dir / "output"
        profile_dir = temp_dir / "profile"
        input_dir.mkdir()
        output_dir.mkdir()
        profile_dir.mkdir()
        source_name = sanitize_filename(media_part.filename)
        if not Path(source_name).suffix and extension:
            source_name = sanitize_filename(f"{source_name}{extension}")
        source_path = input_dir / source_name
        source_path.write_bytes(media_part.content_bytes)
        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "html",
            "--outdir",
            str(output_dir),
            str(source_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=SOFFICE_EMBEDDED_IMAGE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            log_progress(verbose, 2, f"LibreOffice executable vanished before scanning {media_part.filename}: {soffice}")
            return []
        except subprocess.TimeoutExpired:
            log_progress(verbose, 1, f"LibreOffice embedded image scan timed out for {media_part.filename}")
            return []
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip().splitlines()
            suffix = f": {stderr[-1]}" if stderr else ""
            log_progress(verbose, 2, f"LibreOffice embedded image scan failed for {media_part.filename}{suffix}")
            return []

        written: list[WrittenAttachment] = []
        media_dir = embedded_image_dir / backup_folder_name
        image_index = 0
        for candidate in sorted(output_dir.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in EMBEDDED_IMAGE_EXTENSIONS:
                continue
            try:
                image_bytes = candidate.read_bytes()
            except OSError:
                continue
            if not image_bytes:
                continue
            guessed_mime_type = guess_mime_type_from_filename(candidate.name)
            mime_type = sniff_image_mime_type(image_bytes) or guessed_mime_type
            if not mime_type.startswith("image/"):
                continue
            image_index += 1
            media_dir.mkdir(parents=True, exist_ok=True)
            relative_member = candidate.relative_to(output_dir).as_posix()
            image_token = f"{media_part.search_token}-loimg{image_index:03d}"
            written.append(
                write_bytes_attachment(
                    embedded_image_dir,
                    media_dir,
                    destination_name=build_libreoffice_embedded_image_filename(
                        media_part.search_token,
                        media_part.filename,
                        relative_member,
                        image_index,
                    ),
                    original_filename=f"{media_part.filename}:{relative_member}",
                    search_token=image_token,
                    mime_type=mime_type,
                    content_bytes=image_bytes,
                    disposition="derived",
                    content_id=None,
                    group_search_token=media_part.search_token,
                    source_attachment_mime_type=media_part.mime_type,
                    source_generation="embedded-image-libreoffice",
                )
            )
    if written:
        log_progress(verbose, 2, f"Extracted {len(written)} LibreOffice embedded image(s) from {media_part.filename}")
    return written


def extract_embedded_images_from_document(
    media_part: BufferedMediaPart,
    embedded_image_dir: Path | None,
    backup_folder_name: str,
    *,
    soffice_path: str | None = None,
    verbose: int = 0,
) -> list[WrittenAttachment]:
    written = extract_zip_embedded_images_from_document(
        media_part,
        embedded_image_dir,
        backup_folder_name,
        verbose=verbose,
    )
    if written:
        return written
    return extract_libreoffice_embedded_images_from_document(
        media_part,
        embedded_image_dir,
        backup_folder_name,
        soffice_path=soffice_path,
        verbose=verbose,
    )


def write_file_attachment(
    backup_dir: Path,
    message_dir: Path,
    source_path: Path,
    *,
    destination_name: str,
    original_filename: str,
    search_token: str,
    disposition: str,
    content_id: str | None,
    group_search_token: str | None = None,
    source_attachment_mime_type: str | None = None,
    source_generation: str | None = None,
    source_page_number: int | None = None,
) -> WrittenAttachment:
    content_bytes = source_path.read_bytes()
    return write_bytes_attachment(
        backup_dir,
        message_dir,
        destination_name=destination_name,
        original_filename=original_filename,
        search_token=search_token,
        mime_type=guess_mime_type_from_filename(destination_name),
        content_bytes=content_bytes,
        disposition=disposition,
        content_id=content_id,
        group_search_token=group_search_token,
        source_attachment_mime_type=source_attachment_mime_type,
        source_generation=source_generation,
        source_page_number=source_page_number,
    )


def convert_audio_to_video_file(
    source_path: Path,
    output_path: Path,
    *,
    original_filename: str,
    search_token: str,
    assume_yes: bool = False,
) -> None:
    ffmpeg_path = resolve_ffmpeg_path(assume_yes=assume_yes)
    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=1280x720:r=1",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "256k",
        "-movflags",
        "+faststart",
        "-metadata",
        f"title={original_filename}",
        "-metadata",
        f"comment=gmail-cleanup marker {search_token}",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to convert audio attachment {original_filename} to video: {detail}") from exc


def write_audio_video_attachment(
    backup_dir: Path,
    message_dir: Path,
    media_part: BufferedMediaPart,
    *,
    assume_yes: bool = False,
) -> WrittenAttachment:
    destination_name = build_audio_video_filename(media_part.search_token, media_part.filename)
    destination = matching_destination(message_dir, destination_name, b"")
    if not destination.exists():
        suffix = attachment_extension(media_part.filename) or ".audio"
        with tempfile.NamedTemporaryFile(
            prefix="gmail-cleanup-audio-",
            suffix=suffix,
            dir=message_dir,
            delete=False,
        ) as handle:
            source_path = Path(handle.name)
            handle.write(media_part.content_bytes)
        try:
            convert_audio_to_video_file(
                source_path,
                destination,
                original_filename=media_part.filename,
                search_token=media_part.search_token,
                assume_yes=assume_yes,
            )
        finally:
            if source_path.exists():
                source_path.unlink()
    content_bytes = destination.read_bytes()
    relative_path = destination.relative_to(backup_dir).as_posix()
    return WrittenAttachment(
        local_path=destination,
        filename=destination.name,
        original_filename=media_part.filename,
        search_token=media_part.search_token,
        mime_type="video/mp4",
        size_bytes=len(content_bytes),
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        relative_path=relative_path,
        disposition=media_part.disposition,
        content_id=media_part.content_id,
        source_attachment_mime_type=media_part.mime_type,
        source_generation="audio-video",
    )
