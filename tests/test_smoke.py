from __future__ import annotations

import py_compile
import subprocess
import sys
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
        py_compile.compile(str(REPO_ROOT / "wh"), doraise=True)
        py_compile.compile(str(REPO_ROOT / "whisper"), doraise=True)

    def test_wh_help(self) -> None:
        result = self.run_script("wh", "help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: wh", result.stdout)

    def test_whisper_help(self) -> None:
        result = self.run_script("whisper", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage", result.stdout)
        self.assertIn("--doctor", result.stdout)

    def test_whisper_doctor(self) -> None:
        result = self.run_script("whisper", "--doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Whisper Doctor", result.stdout)
        self.assertIn("Selected backend", result.stdout)
