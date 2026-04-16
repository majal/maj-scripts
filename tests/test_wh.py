from __future__ import annotations

import io
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.support import load_script_module


class WhArgumentRewriteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wh = load_script_module("wh")

    def test_send_injects_short_code_length(self) -> None:
        args = self.wh.build_wormhole_args(["send", "file.zip"])
        self.assertEqual(args, ["send", "--code-length=4", "file.zip"])

    def test_tx_alias_normalizes_and_injects(self) -> None:
        args = self.wh.build_wormhole_args(["tx", "file.zip"])
        self.assertEqual(args, ["send", "--code-length=4", "file.zip"])

    def test_receive_allocate_injects_short_code_length(self) -> None:
        args = self.wh.build_wormhole_args(["receive", "--allocate"])
        self.assertEqual(args, ["receive", "--code-length=4", "--allocate"])

    def test_plain_receive_stays_unchanged(self) -> None:
        args = self.wh.build_wormhole_args(["receive"])
        self.assertEqual(args, ["receive"])

    def test_existing_code_length_is_preserved(self) -> None:
        args = self.wh.build_wormhole_args(["send", "--code-length=7", "file.zip"])
        self.assertEqual(args, ["send", "--code-length=7", "file.zip"])

    def test_explicit_code_suppresses_code_length_injection(self) -> None:
        args = self.wh.build_wormhole_args(["send", "--code", "7-purple-lantern", "file.zip"])
        self.assertEqual(args, ["send", "--code", "7-purple-lantern", "file.zip"])

    def test_leading_flags_are_ignored_when_finding_command(self) -> None:
        args = self.wh.build_wormhole_args(["--verify", "send", "file.zip"])
        self.assertEqual(args, ["--verify", "send", "--code-length=4", "file.zip"])


class WhMissingDependencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wh = load_script_module("wh")

    def test_missing_wormhole_exits_when_install_is_declined(self) -> None:
        with (
            mock.patch.object(self.wh.shutil, "which", return_value=None),
            mock.patch.object(self.wh, "detect_os", return_value="linux"),
            mock.patch.object(self.wh, "detect_pkg_manager", return_value="apt-get"),
            mock.patch.object(self.wh, "confirm", return_value=False),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            with self.assertRaises(SystemExit) as raised:
                self.wh.ensure_wormhole()

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("Install canceled.", stdout.getvalue())

    def test_missing_wormhole_propagates_failed_install_exit_code(self) -> None:
        with (
            mock.patch.object(self.wh.shutil, "which", return_value=None),
            mock.patch.object(self.wh, "detect_os", return_value="linux"),
            mock.patch.object(self.wh, "detect_pkg_manager", return_value="apt-get"),
            mock.patch.object(self.wh, "confirm", return_value=True),
            mock.patch.object(self.wh.subprocess, "run", return_value=types.SimpleNamespace(returncode=42)),
            redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.wh.ensure_wormhole()

        self.assertEqual(raised.exception.code, 42)
