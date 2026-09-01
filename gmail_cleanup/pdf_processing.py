"""PDF rendering/extraction primitives for gmail-cleanup: page counting,
embedded-image inspection (pdfimages -list parsing, scanned-PDF heuristic),
page-to-image rendering (pdftocairo) and direct image extraction
(pdfimages), native text extraction (pdftotext) and OCR fallback
(ocrmypdf/tesseract), and the ``build_pdf_text_blocks`` orchestrator that
picks between native and OCR text per the configured PDF text mode. Also
holds ``extract_message_search_text``/``html_to_text``, which pull readable
text out of a raw message for the PDF-password candidate generator to seed
guesses from.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md). The report
grouped this region together with PDF password cracking as "genuinely
tangled... these two call each other." An AST-based call-graph trace of
every function from ``pdf_password_args`` through ``extract_message_search_
text`` found the opposite direction only: nothing in this module calls into
the password-cracking cluster (``resolve_pdf_password`` and friends,
deliberately left in the top-level script this pass -- see the report's
2026-09-01 follow-up section for why); the password-cracking cluster calls
*into* this module (``resolve_pdf_password`` calls ``pdf_page_count``,
``write_pdf_outputs`` calls several of these functions directly). Every
external name this module's functions reference resolves to the standard
library or an already-extracted module: gmail_cleanup.constants,
gmail_cleanup.models, gmail_cleanup.message_utils (parse_email_message),
gmail_cleanup.naming (build_pdf_page_filename/build_pdf_page_search_token),
gmail_cleanup.attachment_writers (write_file_attachment),
gmail_cleanup.tool_paths (the resolve_pdf*/resolve_tesseract_path/
resolve_ffmpeg_path/resolve_ocrmypdf_path family), and gmail_cleanup.config
(log_progress). No behavior changes.
"""

from __future__ import annotations

import html
import shutil
import subprocess
import tempfile
from pathlib import Path

from gmail_cleanup.attachment_writers import write_file_attachment
from gmail_cleanup.config import log_progress
from gmail_cleanup.constants import (
    HTML_TAG_PATTERN,
    PDF_NOTE_EXTENSIONS,
    WHITESPACE_PATTERN,
)
from gmail_cleanup.message_utils import parse_email_message
from gmail_cleanup.models import BufferedMediaPart, ExtractionSettings, PdfTextBlock, WrittenAttachment
from gmail_cleanup.naming import build_pdf_page_filename, build_pdf_page_search_token
from gmail_cleanup.tool_paths import (
    resolve_ffmpeg_path,
    resolve_ocrmypdf_path,
    resolve_pdfimages_path,
    resolve_pdfinfo_path,
    resolve_pdftocairo_path,
    resolve_pdftotext_path,
    resolve_tesseract_path,
)


def pdf_password_args(password: str | None) -> list[str]:
    return ["-upw", password] if password else []


def pdf_page_count(pdf_path: Path, *, password: str | None = None, assume_yes: bool = False) -> int:
    pdfinfo_path = resolve_pdfinfo_path(assume_yes=assume_yes)
    try:
        result = subprocess.run([pdfinfo_path, *pdf_password_args(password), str(pdf_path)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to inspect PDF page count in {pdf_path}: {detail}") from exc
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError as exc:
                raise RuntimeError(f"Unexpected Pages value in pdfinfo output for {pdf_path}") from exc
    raise RuntimeError(f"Could not determine PDF page count for {pdf_path}")


def parse_pdfimages_list_output(output: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("page") or line.startswith("-"):
            continue
        tokens = line.split()
        if len(tokens) < 16:
            continue
        try:
            rows.append(
                {
                    "page": int(tokens[0]),
                    "num": int(tokens[1]),
                    "type": tokens[2].lower(),
                    "width": int(tokens[3]),
                    "height": int(tokens[4]),
                    "enc": tokens[8].lower(),
                    "x_ppi": float(tokens[12]) if tokens[12].replace(".", "", 1).isdigit() else None,
                    "y_ppi": float(tokens[13]) if tokens[13].replace(".", "", 1).isdigit() else None,
                }
            )
        except ValueError:
            continue
    return rows


def list_pdf_image_rows(pdf_path: Path, *, password: str | None = None, assume_yes: bool = False) -> list[dict[str, object]]:
    pdfimages_path = resolve_pdfimages_path(assume_yes=assume_yes)
    try:
        result = subprocess.run(
            [pdfimages_path, *pdf_password_args(password), "-list", str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to inspect PDF images in {pdf_path}: {detail}") from exc
    return parse_pdfimages_list_output(result.stdout)


def is_probably_scanned_pdf(pdf_path: Path, page_count: int, *, password: str | None = None, assume_yes: bool = False) -> bool:
    rows = [row for row in list_pdf_image_rows(pdf_path, password=password, assume_yes=assume_yes) if row.get("type") == "image"]
    if page_count < 1 or len(rows) < page_count:
        return False
    for page_number in range(1, page_count + 1):
        page_rows = [row for row in rows if row.get("page") == page_number]
        if not page_rows:
            return False
        largest = max(page_rows, key=lambda row: int(row["width"]) * int(row["height"]))
        if int(largest["width"]) < 1000 or int(largest["height"]) < 1000:
            return False
    return True


def render_pdf_output_suffix(render_format: str) -> str:
    return ".jpg" if render_format == "jpg" else ".png"


def convert_image_file(
    source_path: Path,
    output_path: Path,
    *,
    render_format: str,
    assume_yes: bool = False,
) -> None:
    ffmpeg_path = resolve_ffmpeg_path(assume_yes=assume_yes)
    command = [ffmpeg_path, "-y", "-i", str(source_path), "-frames:v", "1"]
    if render_format == "jpg":
        command.extend(["-q:v", "2"])
    command.append(str(output_path))
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to convert extracted image {source_path}: {detail}") from exc


def choose_pdf_image_candidate(candidates: list[Path]) -> Path | None:
    allowed = {".png", ".jpg", ".jpeg", ".jp2", ".jbig2", ".jb2", ".tif", ".tiff", ".pbm", ".pgm", ".ppm", ".ccitt"}
    filtered = [candidate for candidate in candidates if candidate.is_file() and candidate.suffix.lower() in allowed]
    if not filtered:
        return None
    return max(filtered, key=lambda candidate: candidate.stat().st_size)


def render_pdf_pages_to_images(
    pdf_path: Path,
    message_dir: Path,
    backup_dir: Path,
    media_part: BufferedMediaPart,
    settings: ExtractionSettings,
    *,
    password: str | None = None,
    verbose: int = 0,
    assume_yes: bool = False,
) -> list[WrittenAttachment]:
    pdftocairo_path = resolve_pdftocairo_path(assume_yes=assume_yes)
    render_format = "png" if settings.pdf_render_format == "auto" else settings.pdf_render_format
    suffix = render_pdf_output_suffix(render_format)
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-pdf-render-", dir=message_dir) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        prefix = temp_dir / "page"
        command = [pdftocairo_path, f"-{'jpeg' if render_format == 'jpg' else 'png'}", "-r", str(settings.pdf_render_dpi)]
        if render_format == "jpg":
            command.extend(["-jpegopt", "quality=95"])
        command.extend([*pdf_password_args(password), str(pdf_path), str(prefix)])
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(f"Failed to render PDF pages from {pdf_path}: {detail}") from exc
        written: list[WrittenAttachment] = []
        rendered_paths = sorted(temp_dir.glob(f"page-*{suffix}"))
        if not rendered_paths:
            raise RuntimeError(f"Rendering produced no page images for {pdf_path}")
        for rendered_path in rendered_paths:
            try:
                page_number = int(rendered_path.stem.rsplit("-", 1)[1])
            except (IndexError, ValueError) as exc:
                raise RuntimeError(f"Unexpected rendered PDF page name: {rendered_path.name}") from exc
            page_token = build_pdf_page_search_token(media_part.search_token, page_number)
            filename = build_pdf_page_filename(page_token, media_part.filename, page_number, suffix)
            written.append(
                write_file_attachment(
                    backup_dir,
                    message_dir,
                    rendered_path,
                    destination_name=filename,
                    original_filename=media_part.filename,
                    search_token=page_token,
                    disposition=media_part.disposition,
                    content_id=media_part.content_id,
                    group_search_token=media_part.search_token,
                    source_attachment_mime_type=media_part.mime_type,
                    source_generation="pdf-render",
                    source_page_number=page_number,
                )
            )
        log_progress(verbose, 2, f"Rendered {len(written)} page image(s) from {media_part.filename}")
        return written


def extract_pdf_images_directly(
    pdf_path: Path,
    message_dir: Path,
    backup_dir: Path,
    media_part: BufferedMediaPart,
    page_count: int,
    *,
    password: str | None = None,
    verbose: int = 0,
    assume_yes: bool = False,
) -> list[WrittenAttachment]:
    pdfimages_path = resolve_pdfimages_path(assume_yes=assume_yes)
    written: list[WrittenAttachment] = []
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-pdf-extract-", dir=message_dir) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        for page_number in range(1, page_count + 1):
            page_prefix = temp_dir / f"page-{page_number:03d}"
            command = [
                pdfimages_path,
                *pdf_password_args(password),
                "-all",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-p",
                str(pdf_path),
                str(page_prefix),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as exc:
                detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
                raise RuntimeError(f"Failed to extract page images from {pdf_path}: {detail}") from exc
            candidates = sorted(temp_dir.glob(f"{page_prefix.name}*"))
            candidate = choose_pdf_image_candidate(candidates)
            if candidate is None:
                raise RuntimeError(f"No suitable direct image was extracted for page {page_number} in {pdf_path}")
            output_path = candidate
            output_suffix = candidate.suffix.lower()
            if output_suffix not in PDF_NOTE_EXTENSIONS:
                output_suffix = ".png"
                converted = temp_dir / f"{page_prefix.name}-converted{output_suffix}"
                convert_image_file(candidate, converted, render_format="png", assume_yes=assume_yes)
                output_path = converted
            page_token = build_pdf_page_search_token(media_part.search_token, page_number)
            filename = build_pdf_page_filename(page_token, media_part.filename, page_number, output_suffix)
            written.append(
                write_file_attachment(
                    backup_dir,
                    message_dir,
                    output_path,
                    destination_name=filename,
                    original_filename=media_part.filename,
                    search_token=page_token,
                    disposition=media_part.disposition,
                    content_id=media_part.content_id,
                    group_search_token=media_part.search_token,
                    source_attachment_mime_type=media_part.mime_type,
                    source_generation="pdf-extract",
                    source_page_number=page_number,
                )
            )
    log_progress(verbose, 2, f"Direct-extracted {len(written)} page image(s) from {media_part.filename}")
    return written


def extract_pdf_text(pdf_path: Path, *, password: str | None = None, assume_yes: bool = False) -> str:
    pdftotext_path = resolve_pdftotext_path(assume_yes=assume_yes)
    try:
        result = subprocess.run(
            [pdftotext_path, *pdf_password_args(password), "-layout", "-nopgbrk", "-q", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to extract PDF text from {pdf_path}: {detail}") from exc
    return WHITESPACE_PATTERN.sub(" ", result.stdout).strip()


def render_pdf_pages_for_ocr(
    pdf_path: Path,
    working_dir: Path,
    settings: ExtractionSettings,
    *,
    password: str | None = None,
    assume_yes: bool = False,
) -> list[Path]:
    pdftocairo_path = resolve_pdftocairo_path(assume_yes=assume_yes)
    prefix = working_dir / "ocr-page"
    command = [pdftocairo_path, "-png", "-r", str(settings.pdf_render_dpi), *pdf_password_args(password), str(pdf_path), str(prefix)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to render PDF pages for OCR from {pdf_path}: {detail}") from exc
    rendered_paths = sorted(working_dir.glob("ocr-page-*.png"))
    if not rendered_paths:
        raise RuntimeError(f"OCR rendering produced no pages for {pdf_path}")
    return rendered_paths


def ocr_image_with_tesseract(image_path: Path, *, assume_yes: bool = False) -> str:
    tesseract_path = resolve_tesseract_path(assume_yes=assume_yes)
    try:
        result = subprocess.run(
            [tesseract_path, str(image_path), "stdout"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Failed to OCR image {image_path}: {detail}") from exc
    return result.stdout.strip()


def extract_pdf_ocr_text(
    pdf_path: Path,
    settings: ExtractionSettings,
    *,
    password: str | None = None,
    assume_yes: bool = False,
) -> str:
    if password is None and shutil.which("ocrmypdf") is not None:
        ocrmypdf_path = resolve_ocrmypdf_path(assume_yes=assume_yes)
        with tempfile.TemporaryDirectory(prefix="gmail-cleanup-ocrmypdf-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            output_pdf = temp_dir / "ocr.pdf"
            sidecar = temp_dir / "ocr.txt"
            command = [
                ocrmypdf_path,
                "--skip-text",
                "--output-type",
                "none",
                "--sidecar",
                str(sidecar),
                str(pdf_path),
                str(output_pdf),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                pass
            else:
                text = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
                if text:
                    return WHITESPACE_PATTERN.sub(" ", text).strip()
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-ocr-render-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        page_paths = render_pdf_pages_for_ocr(pdf_path, temp_dir, settings, password=password, assume_yes=assume_yes)
        chunks = [ocr_image_with_tesseract(page_path, assume_yes=assume_yes) for page_path in page_paths]
    text = "\n".join(chunk for chunk in chunks if chunk.strip())
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def build_pdf_text_blocks(
    pdf_path: Path,
    media_part: BufferedMediaPart,
    settings: ExtractionSettings,
    *,
    password: str | None = None,
    verbose: int = 0,
    assume_yes: bool = False,
) -> list[PdfTextBlock]:
    if settings.pdf_text_mode == "none":
        return []
    text_blocks: list[PdfTextBlock] = []
    native_text = ""
    if settings.pdf_text_mode in {"native", "auto"}:
        try:
            native_text = extract_pdf_text(pdf_path, password=password, assume_yes=assume_yes)
        except RuntimeError as exc:
            log_progress(verbose, 1, f"Skipping native retained text for {media_part.filename} [{exc}]")
        else:
            if native_text:
                text_blocks.append(
                    PdfTextBlock(
                        original_filename=media_part.filename,
                        group_search_token=media_part.search_token,
                        text=native_text,
                        source="native",
                    )
                )
    if settings.pdf_text_mode == "native":
        return text_blocks
    if settings.pdf_text_mode == "auto" and native_text:
        return text_blocks
    try:
        ocr_text = extract_pdf_ocr_text(pdf_path, settings, password=password, assume_yes=assume_yes)
    except RuntimeError as exc:
        log_progress(verbose, 1, f"Skipping OCR retained text for {media_part.filename} [{exc}]")
        return text_blocks
    if ocr_text:
        text_blocks.append(
            PdfTextBlock(
                original_filename=media_part.filename,
                group_search_token=media_part.search_token,
                text=ocr_text,
                source="ocr",
            )
        )
    return text_blocks


def html_to_text(html_text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", html.unescape(HTML_TAG_PATTERN.sub(" ", html_text))).strip()


def extract_message_search_text(raw_bytes: bytes) -> str:
    message = parse_email_message(raw_bytes)
    chunks: list[str] = []
    for header_name in ("subject", "from", "to", "date"):
        value = message.get(header_name)
        if value:
            chunks.append(value)
    for part in message.walk():
        if (part.get_content_disposition() or "").lower() == "attachment":
            continue
        content_type = part.get_content_type().lower()
        if content_type == "text/plain":
            chunks.append(part.get_content())
        elif content_type == "text/html":
            chunks.append(html_to_text(part.get_content()))
    return "\n".join(chunk for chunk in chunks if chunk).strip()
