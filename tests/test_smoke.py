from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
import unittest

from tests.support import REPO_ROOT


class SmokeTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_scripts_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            py_compile.compile(str(REPO_ROOT / "gmail-cleanup"), cfile=f"{tmpdir}/gmail_cleanup.pyc", doraise=True)
            py_compile.compile(str(REPO_ROOT / "wh"), cfile=f"{tmpdir}/wh.pyc", doraise=True)
            py_compile.compile(str(REPO_ROOT / "whisper"), cfile=f"{tmpdir}/whisper.pyc", doraise=True)

    def test_gmail_cleanup_help(self) -> None:
        top_level = self.run_script("gmail-cleanup", "--help")
        self.assertEqual(top_level.returncode, 0, top_level.stderr)
        self.assertIn("extract-media", top_level.stdout)
        self.assertIn("report", top_level.stdout)
        self.assertIn("index", top_level.stdout)
        self.assertIn("doctor", top_level.stdout)

        result = self.run_script("gmail-cleanup", "extract-media", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--backup-dir", result.stdout)
        self.assertIn("--apply", result.stdout)
        self.assertIn("--preset", result.stdout)

        report = self.run_script("gmail-cleanup", "report", "--help")
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("--query", report.stdout)
        self.assertIn("--use-index", report.stdout)

        index = self.run_script("gmail-cleanup", "index", "build", "--help")
        self.assertEqual(index.returncode, 0, index.stderr)
        self.assertIn("--index-db", index.stdout)

    def test_gmail_cleanup_doctor_json(self) -> None:
        result = self.run_script("gmail-cleanup", "doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "doctor")
        self.assertIn("checks", payload)
        self.assertIn("overall_status", payload)

    def test_wh_help(self) -> None:
        result = self.run_script("wh", "help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: wh", result.stdout)

    def test_whisper_help(self) -> None:
        result = self.run_script("whisper", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage", result.stdout)
        self.assertIn("--doctor", result.stdout)
        self.assertIn("--doctor --deep", result.stdout)
        self.assertIn("--make-sample-media", result.stdout)

    def test_whisper_doctor(self) -> None:
        result = self.run_script("whisper", "--doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Whisper Doctor", result.stdout)
        self.assertIn("Selected backend", result.stdout)
        doctor_rows = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("  ") and ":" in line
        ]
        value_columns = set()
        for line in doctor_rows:
            value_start = line.index(":") + 1
            while value_start < len(line) and line[value_start] == " ":
                value_start += 1
            value_columns.add(value_start)
        self.assertEqual(len(value_columns), 1, result.stdout)

    def test_whisper_doctor_json(self) -> None:
        result = self.run_script("whisper", "--doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "doctor")
        self.assertIn("runtime", payload)
        self.assertIn("ffmpeg", payload)
