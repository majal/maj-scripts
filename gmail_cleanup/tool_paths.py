"""External-tool path resolution for gmail-cleanup: thin wrappers around
ensure_system_tool()/optional_tool_path() for each PDF, OCR, and AV
(exiftool/ffmpeg) command-line dependency used elsewhere in the script.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
Depends only on the standard library plus gmail_cleanup.system_tools
(ensure_system_tool, optional_tool_path -- already extracted), so it moved
as the seventh self-contained piece. No behavior changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from gmail_cleanup.system_tools import ensure_system_tool, optional_tool_path


def resolve_pdfimages_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("pdfimages", "poppler", "to extract images from PDFs", assume_yes=assume_yes)


def resolve_pdfinfo_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("pdfinfo", "poppler", "to inspect PDFs", assume_yes=assume_yes)


def resolve_pdftocairo_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("pdftocairo", "poppler", "to render PDF pages", assume_yes=assume_yes)


def resolve_pdftotext_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("pdftotext", "poppler", "to extract searchable text from PDFs", assume_yes=assume_yes)


def resolve_qpdf_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("qpdf", "qpdf", "to verify or decrypt PDF passwords", assume_yes=assume_yes)


def resolve_pdfcrack_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("pdfcrack", "pdfcrack", "to try bounded PDF password recovery", assume_yes=assume_yes)


def find_pdf2john_path() -> Path | None:
    candidates = [
        optional_tool_path("pdf2john"),
        optional_tool_path("pdf2john.py"),
        optional_tool_path("pdf2john.pl"),
        "/usr/share/john/pdf2john",
        "/usr/share/john/pdf2john.py",
        "/usr/share/john/pdf2john.pl",
        "/usr/lib/john/pdf2john",
        "/usr/lib/john/pdf2john.py",
        "/usr/lib/john/pdf2john.pl",
        "/usr/libexec/john/pdf2john",
        "/usr/libexec/john/pdf2john.py",
        "/usr/libexec/john/pdf2john.pl",
        "/opt/homebrew/share/john/pdf2john.py",
        "/opt/homebrew/share/john/pdf2john.pl",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def john_runtime_home(john_path: str) -> Path:
    return Path(john_path).expanduser().resolve().parent


def resolve_ocrmypdf_path(*, assume_yes: bool = False) -> str:
    path = shutil.which("ocrmypdf")
    if path is not None:
        return path
    return ensure_system_tool("ocrmypdf", "ocrmypdf", "to OCR scanned PDFs", assume_yes=assume_yes)


def resolve_tesseract_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("tesseract", "tesseract", "to OCR scanned PDFs", assume_yes=assume_yes)


def resolve_exiftool_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("exiftool", "exiftool", "to stamp marker metadata into saved files", assume_yes=assume_yes)


def resolve_ffmpeg_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("ffmpeg", "ffmpeg", "to stamp video metadata and convert extracted images", assume_yes=assume_yes)


def resolve_ffprobe_path(*, assume_yes: bool = False) -> str:
    return ensure_system_tool("ffprobe", "ffmpeg", "to preserve existing video metadata", assume_yes=assume_yes)
