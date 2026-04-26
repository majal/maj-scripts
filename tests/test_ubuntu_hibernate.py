from __future__ import annotations

import unittest

from tests.support import load_script_module


class UbuntuHibernateUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script_module("ubuntu-hibernate")

    def test_parse_proc_swaps(self) -> None:
        swaps = self.module.parse_proc_swaps(
            """Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority
/dev/dm-1                               partition\t20971516\t0\t-2
/swapfile                               file\t\t1048576\t\t0\t-3
"""
        )

        self.assertEqual(len(swaps), 2)
        self.assertEqual(swaps[0].name, "/dev/dm-1")
        self.assertEqual(swaps[0].size_bytes, 20971516 * 1024)
        self.assertFalse(swaps[0].is_file)
        self.assertTrue(swaps[1].is_file)

    def test_choose_resume_candidate_prefers_largest_supported_block_swap(self) -> None:
        small = self.module.SwapEntry("/dev/sda2", "partition", 4 * 1024**3, 0, -2, uuid="small")
        large = self.module.SwapEntry("/dev/mapper/swap", "partition", 16 * 1024**3, 0, -1, uuid="large")
        file_swap = self.module.SwapEntry("/swapfile", "file", 64 * 1024**3, 0, -3, uuid="file")
        zram = self.module.SwapEntry("/dev/zram0", "partition", 64 * 1024**3, 0, 100, uuid="zram")

        candidate = self.module.choose_resume_candidate([small, large, file_swap, zram])

        self.assertIs(candidate, large)

    def test_setup_blockers_require_supported_os_and_resume_target(self) -> None:
        report = {
            "host": {
                "os_id": "ubuntu",
                "version_id": "24.04",
            },
            "recommended_resume": None,
            "checks": [
                {"id": "kernel-state", "status": "pass", "summary": "ok"},
                {"id": "swap", "status": "warn", "summary": "swapfile only"},
                {"id": "initramfs", "status": "pass", "summary": "ok"},
                {"id": "cmdline", "status": "info", "summary": "ok"},
                {"id": "encryption", "status": "info", "summary": "ok"},
            ],
        }

        blockers = self.module.setup_blockers(report, allow_unsupported=False)

        self.assertTrue(any("Ubuntu 26.04" in blocker for blocker in blockers))
        self.assertIn("No block-device swap UUID is available for RESUME=.", blockers)

    def test_markdown_report_contains_checks_and_swap(self) -> None:
        report = {
            "generated_at": "2026-04-26T00:00:00+00:00",
            "supported_target": "Ubuntu 26.04",
            "overall_status": "pass",
            "host": {
                "os_pretty_name": "Ubuntu 26.04 LTS",
                "kernel": "7.0.0-test",
            },
            "checks": [
                {
                    "title": "Swap space",
                    "status": "pass",
                    "summary": "ready",
                    "details": ["candidate found"],
                }
            ],
            "swaps": [
                {
                    "name": "/dev/mapper/swap",
                    "kind": "partition",
                    "size_bytes": 16 * 1024**3,
                    "uuid": "abc",
                }
            ],
        }

        markdown = self.module.report_to_markdown(report)

        self.assertIn("# ubuntu-hibernate report", markdown)
        self.assertIn("### Swap space", markdown)
        self.assertIn("`/dev/mapper/swap`", markdown)


if __name__ == "__main__":
    unittest.main()
