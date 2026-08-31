"""System-tool discovery and install helpers for gmail-cleanup: OS/package
manager detection, optional-tool lookup, interactive install prompts, and
the ensure_system_tool() gate used by every external-tool resolver (pdfimages,
exiftool, ffmpeg, etc.) elsewhere in the script.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
No behavior changes -- this module depends only on the standard library, so
it moved as the fourth self-contained piece.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def detect_os() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def detect_pkg_manager(os_name: str) -> str:
    if os_name == "macos" and shutil.which("brew"):
        return "brew"
    if os_name == "windows":
        if shutil.which("winget"):
            return "winget"
        if shutil.which("choco"):
            return "choco"
        return "unknown"
    for candidate in ("apt-get", "dnf", "yum", "pacman", "zypper", "apk", "snap"):
        if shutil.which(candidate):
            return candidate
    return "unknown"


def optional_tool_path(executable: str) -> str | None:
    return shutil.which(executable)


def confirm(prompt: str, *, default_yes: bool = True, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower() if sys.stdin.isatty() else ""
    except EOFError:
        return False
    if default_yes:
        return answer not in {"n", "no"}
    return answer in {"y", "yes"}


def run_install_command(command: str, os_name: str) -> int:
    shell = os.environ.get("COMSPEC", "cmd.exe") if os_name == "windows" else os.environ.get("SHELL", "/bin/sh")
    if os_name == "windows":
        return subprocess.run([shell, "/c", command], check=False).returncode
    return subprocess.run([shell, "-lc", command], check=False).returncode


def dependency_install_command(tool_key: str, os_name: str, pkg_manager: str) -> str | None:
    commands = {
        ("gmail-api-python", "macos", "brew"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "windows", "winget"): "py -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "windows", "choco"): "py -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "apt-get"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "dnf"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "yum"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "pacman"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "zypper"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("gmail-api-python", "linux", "apk"): "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2",
        ("exiftool", "macos", "brew"): "brew install exiftool",
        ("exiftool", "windows", "winget"): "winget install -e --id OliverBetz.ExifTool --accept-package-agreements --accept-source-agreements",
        ("exiftool", "windows", "choco"): "choco install exiftool -y",
        ("exiftool", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y libimage-exiftool-perl",
        ("exiftool", "linux", "dnf"): "sudo dnf install -y perl-Image-ExifTool",
        ("exiftool", "linux", "yum"): "sudo yum install -y perl-Image-ExifTool",
        ("exiftool", "linux", "pacman"): "sudo pacman -S --needed perl-image-exiftool",
        ("exiftool", "linux", "zypper"): "sudo zypper install -y perl-Image-ExifTool",
        ("exiftool", "linux", "apk"): "sudo apk add perl-image-exiftool",
        ("ffmpeg", "macos", "brew"): "brew install ffmpeg",
        ("ffmpeg", "windows", "winget"): "winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements",
        ("ffmpeg", "windows", "choco"): "choco install ffmpeg -y",
        ("ffmpeg", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y ffmpeg",
        ("ffmpeg", "linux", "dnf"): "sudo dnf install -y ffmpeg",
        ("ffmpeg", "linux", "yum"): "sudo yum install -y ffmpeg",
        ("ffmpeg", "linux", "pacman"): "sudo pacman -S --needed ffmpeg",
        ("ffmpeg", "linux", "zypper"): "sudo zypper install -y ffmpeg",
        ("ffmpeg", "linux", "apk"): "sudo apk add ffmpeg",
        ("poppler", "macos", "brew"): "brew install poppler",
        ("poppler", "windows", "winget"): "winget install -e --id oschwartz10612.Poppler --accept-package-agreements --accept-source-agreements",
        ("poppler", "windows", "choco"): "choco install poppler -y",
        ("poppler", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y poppler-utils",
        ("poppler", "linux", "dnf"): "sudo dnf install -y poppler-utils",
        ("poppler", "linux", "yum"): "sudo yum install -y poppler-utils",
        ("poppler", "linux", "pacman"): "sudo pacman -S --needed poppler",
        ("poppler", "linux", "zypper"): "sudo zypper install -y poppler-tools",
        ("poppler", "linux", "apk"): "sudo apk add poppler-utils",
        ("qpdf", "macos", "brew"): "brew install qpdf",
        ("qpdf", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y qpdf",
        ("qpdf", "linux", "dnf"): "sudo dnf install -y qpdf",
        ("qpdf", "linux", "yum"): "sudo yum install -y qpdf",
        ("qpdf", "linux", "pacman"): "sudo pacman -S --needed qpdf",
        ("qpdf", "linux", "zypper"): "sudo zypper install -y qpdf",
        ("qpdf", "linux", "apk"): "sudo apk add qpdf",
        ("pdfcrack", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y pdfcrack",
        ("pdfcrack", "linux", "dnf"): "sudo dnf install -y pdfcrack",
        ("pdfcrack", "linux", "yum"): "sudo yum install -y pdfcrack",
        ("pdfcrack", "linux", "pacman"): "sudo pacman -S --needed pdfcrack",
        ("pdfcrack", "linux", "zypper"): "sudo zypper install -y pdfcrack",
        ("john", "macos", "brew"): "brew install john-jumbo",
        ("john", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y john",
        ("john", "linux", "dnf"): "sudo dnf install -y john",
        ("john", "linux", "yum"): "sudo yum install -y john",
        ("john", "linux", "pacman"): "sudo pacman -S --needed john",
        ("john", "linux", "zypper"): "sudo zypper install -y john",
        ("hashcat", "macos", "brew"): "brew install hashcat",
        ("hashcat", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y hashcat",
        ("hashcat", "linux", "dnf"): "sudo dnf install -y hashcat",
        ("hashcat", "linux", "yum"): "sudo yum install -y hashcat",
        ("hashcat", "linux", "pacman"): "sudo pacman -S --needed hashcat",
        ("hashcat", "linux", "zypper"): "sudo zypper install -y hashcat",
        ("ocrmypdf", "macos", "brew"): "brew install ocrmypdf",
        ("ocrmypdf", "windows", "winget"): "py -m pip install --user ocrmypdf",
        ("ocrmypdf", "windows", "choco"): "py -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "apt-get"): "python3 -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "dnf"): "python3 -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "yum"): "python3 -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "pacman"): "python3 -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "zypper"): "python3 -m pip install --user ocrmypdf",
        ("ocrmypdf", "linux", "apk"): "python3 -m pip install --user ocrmypdf",
        ("tesseract", "macos", "brew"): "brew install tesseract",
        ("tesseract", "windows", "winget"): "winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements",
        ("tesseract", "windows", "choco"): "choco install tesseract -y",
        ("tesseract", "linux", "apt-get"): "sudo apt-get update && sudo apt-get install -y tesseract-ocr",
        ("tesseract", "linux", "dnf"): "sudo dnf install -y tesseract",
        ("tesseract", "linux", "yum"): "sudo yum install -y tesseract",
        ("tesseract", "linux", "pacman"): "sudo pacman -S --needed tesseract",
        ("tesseract", "linux", "zypper"): "sudo zypper install -y tesseract-ocr",
        ("tesseract", "linux", "apk"): "sudo apk add tesseract-ocr",
    }
    command = commands.get((tool_key, os_name, pkg_manager))
    if command is not None:
        return command
    if tool_key == "gmail-api-python":
        return "py -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2" if os_name == "windows" else "python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2"
    return None


def ensure_system_tool(executable: str, tool_key: str, purpose: str, *, assume_yes: bool = False) -> str:
    path = shutil.which(executable)
    if path is not None:
        return path
    os_name = detect_os()
    pkg_manager = detect_pkg_manager(os_name)
    command = dependency_install_command(tool_key, os_name, pkg_manager)
    print(f"`{executable}` is required {purpose} but was not found on PATH.", file=sys.stderr)
    if command is not None:
        print(f"Detected OS: {os_name}", file=sys.stderr)
        print(f"Detected package manager: {pkg_manager}", file=sys.stderr)
        print(f"Planned install command: {command}", file=sys.stderr)
        if confirm(f"Run this install command now so gmail-cleanup can continue?", default_yes=True, assume_yes=assume_yes):
            result = run_install_command(command, os_name)
            if result != 0:
                raise RuntimeError(f"Install command failed with exit code {result}: {command}")
            path = shutil.which(executable)
            if path is not None:
                return path
    raise RuntimeError(f"Missing `{executable}`. Install it first so gmail-cleanup can continue.")
