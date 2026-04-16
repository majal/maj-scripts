from __future__ import annotations

import unittest

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
