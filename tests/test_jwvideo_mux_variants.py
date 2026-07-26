from __future__ import annotations

import unittest

from tests.support import load_script_module


class VideoVariantAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script_module("jwvideo-mux")

    def test_candidate_intervals_requires_sustained_drop(self) -> None:
        scores = [0.983] * 30 + [0.83] * 15 + [0.983] * 30
        threshold, intervals = self.module.candidate_intervals(scores, 30.0)
        self.assertLessEqual(threshold, 0.95)
        self.assertEqual(intervals, [(1.0, 1.5)])

    def test_candidate_intervals_rejects_single_frame_noise(self) -> None:
        scores = [0.983] * 30 + [0.83] + [0.983] * 30
        _, intervals = self.module.candidate_intervals(scores, 30.0)
        self.assertEqual(intervals, [])
