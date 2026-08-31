"""Cross-platform "send to trash" helpers for gmail-cleanup: OS-native
trash/recycle-bin integration (macOS Finder, Windows Recycle Bin, Linux XDG
trash spec) used when discarding processed PDF originals.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
Depends only on the standard library plus gmail_cleanup.system_tools
(detect_os, already extracted), so it moved as the fifth self-contained
piece. No behavior changes.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from gmail_cleanup.system_tools import detect_os


def send_path_to_trash(path: Path, *, assume_yes: bool = False) -> None:
    os_name = detect_os()
    if os_name == "linux":
        move_path_to_xdg_trash(path)
        return
    if os_name == "macos":
        osa_path = shutil.which("osascript")
        if osa_path is None:
            raise RuntimeError("Missing osascript. It is required to move processed PDFs to the Trash on macOS.")
        subprocess.run(
            [
                osa_path,
                "-e",
                'on run argv',
                "-e",
                'tell application "Finder" to delete POSIX file (item 1 of argv)',
                "-e",
                "end run",
                str(path),
            ],
            check=True,
        )
        return
    if os_name == "windows":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            raise RuntimeError("Missing PowerShell. It is required to move processed PDFs to the Recycle Bin.")
        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($args[0], 'OnlyErrorDialogs', 'SendToRecycleBin')",
                str(path),
            ],
            check=True,
        )
        return
    raise RuntimeError(f"Unsupported OS for trash support: {os_name}")


def unique_trash_target(directory: Path, filename: str) -> Path:
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


def move_path_to_xdg_trash(path: Path) -> None:
    trash_root = Path.home() / ".local" / "share" / "Trash"
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"
    files_dir.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)
    trashed_path = unique_trash_target(files_dir, path.name)
    shutil.move(str(path), str(trashed_path))
    info_path = info_dir / f"{trashed_path.name}.trashinfo"
    info_payload = "\n".join(
        (
            "[Trash Info]",
            f"Path={quote(str(path.resolve()), safe='/')}",
            f"DeletionDate={datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S')}",
            "",
        )
    )
    info_path.write_text(info_payload, encoding="utf-8")
