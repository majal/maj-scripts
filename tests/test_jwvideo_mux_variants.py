from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import load_script_module

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None
MPV_AVAILABLE = shutil.which("mpv") is not None


class VideoVariantPureLogicTest(unittest.TestCase):
    """Fast, no-ffmpeg tests for the pure-Python statistics/planning helpers."""

    def setUp(self) -> None:
        self.module = load_script_module("jwvideo-mux")

    def test_color_print_replaces_unsupported_console_characters(self) -> None:
        buffer = io.BytesIO()
        console = io.TextIOWrapper(buffer, encoding="cp1252")
        original_stdout = self.module.sys.stdout
        try:
            self.module.sys.stdout = console
            self.module.color_print("✓ complete", "32")
            console.flush()
        finally:
            self.module.sys.stdout = original_stdout
        self.assertIn("? complete", buffer.getvalue().decode("cp1252"))

    def test_candidate_intervals_requires_sustained_drop(self) -> None:
        # 60-frame dip = 2.0s at 30fps, comfortably clears the 1.5s default.
        scores = [0.983] * 60 + [0.83] * 60 + [0.983] * 60
        threshold, intervals = self.module.candidate_intervals(scores, 30.0)
        self.assertLessEqual(threshold, 0.95)
        self.assertEqual(intervals, [(2.0, 4.0)])

    def test_candidate_intervals_rejects_single_frame_noise(self) -> None:
        scores = [0.983] * 30 + [0.83] + [0.983] * 30
        _, intervals = self.module.candidate_intervals(scores, 30.0)
        self.assertEqual(intervals, [])

    def test_candidate_intervals_default_min_seconds_rejects_subsecond_dip(self) -> None:
        # A dip well under the new 1.5s default (0.5s here) is exactly the kind of ordinary
        # encoding-level jitter that used to produce false "localized" candidates.
        scores = [0.983] * 30 + [0.83] * 15 + [0.983] * 30
        _, intervals = self.module.candidate_intervals(scores, 30.0)
        self.assertEqual(intervals, [])

    def test_candidate_intervals_min_seconds_is_configurable(self) -> None:
        scores = [0.983] * 30 + [0.83] * 15 + [0.983] * 30
        _, intervals = self.module.candidate_intervals(scores, 30.0, min_seconds=0.4)
        self.assertEqual(intervals, [(1.0, 1.5)])

    def test_candidate_intervals_min_threshold_prevents_pathological_collapse(self) -> None:
        # Real SCE footage produced this exact shape: three roughly equal-sized clusters spread across
        # the clip (noise throughout rather than one clean window) drive median - 8*mad deeply negative,
        # at which point nothing could ever be flagged and a genuinely dissimilar pair reports a confident
        # "visually_same". A floor fixes it without needing a cap (cap only bounds threshold from above).
        scores = [0.70] * 170 + [0.85] * 170 + [1.0] * 163
        threshold_uncapped, intervals_uncapped = self.module.candidate_intervals(scores, 30.0, min_seconds=1.0)
        self.assertLess(threshold_uncapped, 0.0)  # confirms the collapse actually happens without a floor
        self.assertEqual(intervals_uncapped, [])  # and that collapse means nothing is ever flagged
        threshold_floored, intervals_floored = self.module.candidate_intervals(
            scores, 30.0, min_seconds=1.0, min_threshold=0.75,
        )
        self.assertEqual(threshold_floored, 0.75)
        self.assertEqual(intervals_floored, [(0.0, 5.666666666666667)])

    def test_candidate_intervals_psnr_style_no_cap(self) -> None:
        # PSNR is unbounded above (dB), unlike SSIM's 0-1 range, so it's used with cap=None.
        scores = [42.0] * 60 + [18.0] * 60 + [42.0] * 60
        threshold, intervals = self.module.candidate_intervals(
            scores, 30.0, min_seconds=1.0, mad_multiplier=6.0, floor_margin=3.0, cap=None,
        )
        self.assertLess(threshold, 42.0)
        self.assertEqual(intervals, [(2.0, 4.0)])

    def test_intersect_intervals(self) -> None:
        a = [(1.0, 3.0), (5.0, 6.0)]
        b = [(2.0, 4.0), (5.5, 5.8)]
        result = self.module._intersect_intervals(a, b)
        self.assertEqual(sorted(result), [(2.0, 3.0), (5.5, 5.8)])

    def test_merge_intervals_coalesces_overlaps_and_touches(self) -> None:
        merged = self.module.merge_intervals([(0.0, 2.0), (1.5, 3.0), (5.0, 5.0), (5.0, 6.0)])
        self.assertEqual(merged, [(0.0, 3.0), (5.0, 6.0)])

    def test_merge_intervals_empty(self) -> None:
        self.assertEqual(self.module.merge_intervals([]), [])

    def test_snap_interval_to_keyframes_expands_outward_only(self) -> None:
        kf = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        start, end = self.module.snap_interval_to_keyframes(2.3, 3.7, kf)
        self.assertEqual((start, end), (2.0, 4.0))

    def test_snap_interval_to_keyframes_no_keyframes_is_noop(self) -> None:
        self.assertEqual(self.module.snap_interval_to_keyframes(2.3, 3.7, []), (2.3, 3.7))

    def test_snap_interval_to_keyframes_beyond_last_keyframe(self) -> None:
        kf = [0.0, 1.0, 2.0]
        start, end = self.module.snap_interval_to_keyframes(1.5, 9.0, kf)
        self.assertEqual((start, end), (1.0, 9.0))

    def test_union_cutpoints_includes_endpoints_and_interval_bounds(self) -> None:
        points = self.module.union_cutpoints({"TG": [(2.0, 4.0)], "HV": [(6.0, 6.5)]}, 10.0)
        self.assertEqual(points, [0.0, 2.0, 4.0, 6.0, 6.5, 10.0])

    def test_plan_adaptive_segments_single_language(self) -> None:
        segments = self.module.plan_adaptive_segments({"TG": [(2.0, 4.0)]}, 10.0)
        self.assertEqual(
            [(s["start"], s["end"], s["divergent_languages"]) for s in segments],
            [(0.0, 2.0, []), (2.0, 4.0, ["TG"]), (4.0, 10.0, [])],
        )

    def test_plan_adaptive_segments_coalesces_common_stretches(self) -> None:
        # TG diverges early, HV diverges late; the untouched middle stretch [2,7] must stay one
        # segment rather than getting needlessly fragmented by unrelated cutpoints.
        segments = self.module.plan_adaptive_segments({"TG": [(1.0, 2.0)], "HV": [(7.0, 8.0)]}, 10.0)
        common = [s for s in segments if not s["divergent_languages"]]
        self.assertEqual([(s["start"], s["end"]) for s in common], [(0.0, 1.0), (2.0, 7.0), (8.0, 10.0)])

    def test_plan_adaptive_segments_no_divergence_is_single_common_segment(self) -> None:
        segments = self.module.plan_adaptive_segments({}, 10.0)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["divergent_languages"], [])

    def test_region_crop_specs_even_split(self) -> None:
        specs = self.module._region_crop_specs(1280, 720, 8)
        self.assertEqual(len(specs), 8)
        self.assertEqual([s.height for s in specs], [90] * 8)
        self.assertEqual([s.y for s in specs], [i * 90 for i in range(8)])
        self.assertTrue(all(s.width == 1280 and s.x == 0 for s in specs))

    def test_region_crop_specs_uneven_split_last_band_absorbs_remainder(self) -> None:
        specs = self.module._region_crop_specs(320, 241, 8)
        self.assertEqual(sum(s.height for s in specs), 241)
        self.assertEqual(specs[-1].y + specs[-1].height, 241)

    def test_region_crop_specs_never_exceeds_pixel_height(self) -> None:
        specs = self.module._region_crop_specs(320, 4, 8)
        self.assertEqual(len(specs), 4)

    def test_region_candidate_intervals_merges_overlapping_strips(self) -> None:
        # Two adjacent strips both dip during the same window -- e.g. a graphic spanning a strip
        # boundary -- should coalesce into one candidate spanning both strips, not two separate ones.
        ssim_by_strip = {
            5: [0.99] * 30 + [0.80] * 45 + [0.99] * 30,
            6: [0.99] * 30 + [0.80] * 45 + [0.99] * 30,
            0: [0.99] * 105,
        }
        psnr_by_strip = {5: [], 6: [], 0: []}
        candidates = self.module.region_candidate_intervals(ssim_by_strip, psnr_by_strip, 30.0, min_seconds=1.0)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["strips"], [5, 6])
        self.assertFalse(candidates[0]["psnr_corroborated"])

    def test_region_candidate_intervals_psnr_corroboration_flag(self) -> None:
        ssim_by_strip = {3: [0.99] * 30 + [0.80] * 45 + [0.99] * 30}
        psnr_by_strip = {3: [40.0] * 30 + [20.0] * 45 + [40.0] * 30}
        candidates = self.module.region_candidate_intervals(ssim_by_strip, psnr_by_strip, 30.0, min_seconds=1.0)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["psnr_corroborated"])

    def test_apply_region_evidence_bumps_visually_same_to_review(self) -> None:
        comparisons = {
            "TG": {
                "classification": "visually_same", "intervals": [],
                "region_candidates": [{"start": 2.0, "end": 5.0, "strips": [6], "psnr_corroborated": True}],
            },
        }
        self.module._apply_region_evidence(comparisons)
        self.assertEqual(comparisons["TG"]["classification"], "review_recommended")

    def test_apply_region_evidence_leaves_no_candidates_untouched(self) -> None:
        comparisons = {"TG": {"classification": "visually_same", "intervals": [], "region_candidates": []}}
        self.module._apply_region_evidence(comparisons)
        self.assertEqual(comparisons["TG"]["classification"], "visually_same")

    def test_apply_region_evidence_counts_cross_language_corroboration(self) -> None:
        shared = {"start": 2.0, "end": 5.0, "strips": [6], "psnr_corroborated": False}
        comparisons = {
            "TG": {"classification": "visually_same", "intervals": [], "region_candidates": [dict(shared)]},
            "HV": {"classification": "visually_same", "intervals": [], "region_candidates": [dict(shared)]},
            "SA": {"classification": "visually_same", "intervals": [], "region_candidates": []},
        }
        self.module._apply_region_evidence(comparisons)
        self.assertEqual(comparisons["TG"]["region_candidates"][0]["corroborating_languages"], 1)
        self.assertEqual(comparisons["HV"]["region_candidates"][0]["corroborating_languages"], 1)

    def test_apply_region_evidence_adds_supplementary_windows_to_localized(self) -> None:
        # Already localized_candidates (whole-frame confidently found a difference elsewhere) --
        # a region candidate outside those windows is useful extra evidence, not a reclassification.
        comparisons = {
            "TG": {
                "classification": "localized_candidates", "intervals": [(50.0, 60.0)],
                "region_candidates": [
                    {"start": 2.0, "end": 5.0, "strips": [6], "psnr_corroborated": False},
                    {"start": 55.0, "end": 58.0, "strips": [2], "psnr_corroborated": False},  # inside existing window
                ],
            },
        }
        self.module._apply_region_evidence(comparisons)
        self.assertEqual(comparisons["TG"]["classification"], "localized_candidates")
        extra = comparisons["TG"]["additional_region_windows"]
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0]["start"], 2.0)

    def test_subtract_intervals_partial_overlap_from_both_sides(self) -> None:
        result = self.module._subtract_intervals([(0.0, 10.0)], [(3.0, 5.0), (7.0, 12.0)])
        self.assertEqual(result, [(0.0, 3.0), (5.0, 7.0)])

    def test_subtract_intervals_no_overlap_is_unchanged(self) -> None:
        result = self.module._subtract_intervals([(0.0, 2.0)], [(5.0, 6.0)])
        self.assertEqual(result, [(0.0, 2.0)])

    def test_subtract_intervals_full_removal(self) -> None:
        result = self.module._subtract_intervals([(2.0, 4.0)], [(0.0, 10.0)])
        self.assertEqual(result, [])

    def test_find_manual_video_entry_matches_folder_and_anchor(self) -> None:
        overrides = {
            "talks": [
                {"folder": "1-0 Orientation", "videos": [{"anchor": "scei_E.mp4", "languages": ["TG"]}]},
                {"folder": "1-1 Learn", "videos": [{"anchor": "jwbvs_E.mp4", "languages": ["HV"]}]},
            ],
        }
        entry = self.module.find_manual_video_entry(overrides, "1-1 Learn", "jwbvs_E.mp4")
        self.assertEqual(entry["languages"], ["HV"])

    def test_find_manual_video_entry_no_match_returns_none(self) -> None:
        overrides = {"talks": [{"folder": "1-0 Orientation", "videos": [{"anchor": "scei_E.mp4"}]}]}
        self.assertIsNone(self.module.find_manual_video_entry(overrides, "1-0 Orientation", "wrong.mp4"))
        self.assertIsNone(self.module.find_manual_video_entry(overrides, "wrong folder", "scei_E.mp4"))

    def test_apply_manual_overrides_confirms_a_missed_window(self) -> None:
        # Auto detector said visually_same; human evidence says otherwise.
        variant_analysis = {"comparisons": {"TG": {"classification": "visually_same", "intervals": []}}}
        manual_video = {"languages": ["TG"], "differences": [{"start_s": 3.25, "end_s": 9.22, "label": "name_plate"}]}
        updated = self.module.apply_manual_overrides(variant_analysis, manual_video)
        record = variant_analysis["comparisons"]["TG"]
        self.assertEqual(updated, ["TG"])
        self.assertEqual(record["classification"], "localized_candidates")
        self.assertEqual(record["intervals"], [(3.25, 9.22)])
        self.assertTrue(record["manual_confirmed"])

    def test_apply_manual_overrides_fallback_ok_subtracts_from_existing_intervals(self) -> None:
        # Auto detector already found this window and confidently flagged it -- a human fallback_ok
        # verdict should still be able to remove it (e.g. "yes it differs, but don't bother splitting").
        variant_analysis = {"comparisons": {"TG": {"classification": "localized_candidates", "intervals": [(494.0, 497.5)]}}}
        manual_video = {
            "languages": ["TG"],
            "differences": [{"start_s": 493.96, "end_s": 497.897, "label": "end_credits", "fallback_ok": True}],
        }
        self.module.apply_manual_overrides(variant_analysis, manual_video)
        record = variant_analysis["comparisons"]["TG"]
        self.assertEqual(record["intervals"], [])
        self.assertEqual(record["classification"], "visually_same")  # nothing real left, so it's just "same"

    def test_apply_manual_overrides_mixed_confirmed_and_fallback_ok(self) -> None:
        variant_analysis = {"comparisons": {"TG": {"classification": "visually_same", "intervals": []}}}
        manual_video = {
            "languages": ["TG"],
            "differences": [
                {"start_s": 33.5, "end_s": 45.479, "label": "story_text"},
                {"start_s": 493.96, "end_s": 497.897, "label": "end_credits", "fallback_ok": True},
            ],
        }
        self.module.apply_manual_overrides(variant_analysis, manual_video)
        record = variant_analysis["comparisons"]["TG"]
        # Only the non-fallback_ok window survives into `intervals`.
        self.assertEqual(record["intervals"], [(33.5, 45.479)])
        self.assertEqual(record["classification"], "localized_candidates")

    def test_apply_manual_overrides_whole_video_same_overrides_incompatible(self) -> None:
        variant_analysis = {"comparisons": {"TG": {"classification": "incompatible", "intervals": []}}}
        manual_video = {"languages": ["TG"], "whole_video_same": True, "differences": []}
        self.module.apply_manual_overrides(variant_analysis, manual_video)
        self.assertEqual(variant_analysis["comparisons"]["TG"]["classification"], "visually_same")

    def test_apply_manual_overrides_skips_language_not_in_comparisons(self) -> None:
        variant_analysis = {"comparisons": {}}
        manual_video = {"languages": ["TG"], "differences": []}
        updated = self.module.apply_manual_overrides(variant_analysis, manual_video)
        self.assertEqual(updated, [])

    def test_sanitize_filename_removes_colon_and_other_unsafe_characters(self) -> None:
        # The real trigger: an embedded ffprobe title containing "Title: Subtitle" renders as
        # "Title/Subtitle" in Finder (macOS displays a literal `:` in a filename as `/`, an HFS-era
        # legacy quirk) and is outright illegal on Windows/NTFS/FAT32.
        self.assertEqual(
            self.module.sanitize_filename("Soten Yoeun: My Search for the True God"),
            "Soten Yoeun My Search for the True God",
        )
        self.assertNotIn("<", self.module.sanitize_filename('a<b>c:d"e/f\\g|h?i*j'))
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, self.module.sanitize_filename(f"x{char}y"))

    def test_sanitize_filename_avoids_merging_a_scripture_style_reference(self) -> None:
        # A colon with no surrounding space (e.g. a chapter:verse citation) must not collapse into a
        # single misleading number -- "Romans 3:2" becoming "Romans 32" reads as a different verse.
        self.assertEqual(self.module.sanitize_filename("Romans 3:2"), "Romans 3 2")

    def test_sanitize_filename_collapses_resulting_whitespace(self) -> None:
        self.assertEqual(self.module.sanitize_filename("a :  b"), "a b")

    def test_sanitize_filename_leaves_ordinary_punctuation_alone(self) -> None:
        # Curly quotes, em dashes, parentheses -- all filesystem-safe, shouldn't be touched.
        name = "Mark Sanderson: “Be in Subjection” (Romans 13:1)"
        self.assertNotIn(":", self.module.sanitize_filename(name))
        self.assertIn("“Be in Subjection”", self.module.sanitize_filename(name))

    def test_write_mpv_command_launcher_is_executable_and_valid_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "Play Tagalog.command"
            self.module.write_mpv_command_launcher(out_path, "presentation-tg.edl", "audio-tg.mka", "subtitles-tg.srt", "tgl")
            self.assertTrue(out_path.exists())
            self.assertTrue(out_path.stat().st_mode & 0o111, "launcher must be executable")
            result = subprocess.run(["bash", "-n", str(out_path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            content = out_path.read_text()
            self.assertIn("presentation-tg.edl", content)
            self.assertIn("--audio-file=", content)
            self.assertIn("--sub-file=", content)
            self.assertIn("--alang=tgl", content)

    def test_write_mpv_command_launcher_omits_missing_audio_and_subs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "Play English.command"
            self.module.write_mpv_command_launcher(out_path, "presentation-e.edl", None, None, "eng")
            content = out_path.read_text()
            self.assertNotIn("--audio-file=", content)
            self.assertNotIn("--sub-file=", content)

    def test_load_manual_overrides_parses_toml_and_fallback_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "overrides.toml"
            toml_path.write_text(
                '[[talks]]\n'
                'folder = "1-0 Orientation"\n\n'
                '  [[talks.videos]]\n'
                '  anchor = "scei_E.mp4"\n'
                '  languages = ["TG"]\n\n'
                '    [[talks.videos.differences]]\n'
                '    start_s = 4.5\n'
                '    end_s = 8.3\n'
                '    label = "name_plate"\n'
                '    fallback_ok = true\n',
                encoding="utf-8",
            )
            overrides = self.module.load_manual_overrides(toml_path)
            entry = self.module.find_manual_video_entry(overrides, "1-0 Orientation", "scei_E.mp4")
            self.assertEqual(entry["differences"][0]["fallback_ok"], True)


class _FfmpegFixtureCase(unittest.TestCase):
    """Shared synthetic-clip fixtures built once per test-class run via ffmpeg lavfi sources.

    All clips derive from the same `testsrc2` pattern/size/rate/duration so that everything outside
    an explicit overlay window is pixel-identical across fixtures. Kept small (320x240, 15fps, 8s,
    ultrafast preset) to stay fast.
    """

    SIZE = "320x240"
    RATE = 15
    DURATION = 8
    GOP = 15  # keyframe every 1s at 15fps

    @classmethod
    def setUpClass(cls) -> None:
        if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
            raise unittest.SkipTest("ffmpeg/ffprobe not installed")
        cls.module = load_script_module("jwvideo-mux")
        cls.tmpdir = tempfile.mkdtemp(prefix="jwvideo-mux-fixtures-")
        cls.root = Path(cls.tmpdir)

        cls.ref = cls._encode(cls.root / "ref.mkv", crf=20)
        cls.same_bytes = cls.root / "same_bytes.mkv"
        shutil.copy2(cls.ref, cls.same_bytes)
        cls.diff_encode = cls._encode(cls.root / "diff_encode.mkv", crf=32)
        cls.localized = cls._encode(
            cls.root / "localized.mkv", crf=20,
            extra_vf="drawbox=x=40:y=40:w=200:h=120:color=red@1.0:t=fill:enable='between(t,2.3,4.6)'",
        )
        cls.incompatible = cls._encode(cls.root / "incompatible.mkv", crf=20, size="160x120")
        cls.globally_dissimilar = cls._encode(
            cls.root / "globally_dissimilar.mkv", crf=20,
            extra_vf="drawbox=x=0:y=0:w=320:h=240:color=gray@0.35:t=fill",  # whole-clip, not windowed
        )

        # Trailing-freeze fixtures: identical 5s of "live" content, then a held final frame for a
        # different length each -- same shape as a per-language end-card/copyright-screen mismatch.
        # Freeze durations must clear trailing_freeze_start's default min_freeze_s (2.0s) to be found.
        cls.tail_short = cls._encode_with_frozen_tail(cls.root / "tail_short.mkv", live_s=5, freeze_s=2.5)
        cls.tail_long = cls._encode_with_frozen_tail(cls.root / "tail_long.mkv", live_s=5, freeze_s=4)
        cls.tail_no_shared_freeze = cls._encode_with_frozen_tail(
            cls.root / "tail_no_shared_freeze.mkv", live_s=3, freeze_s=4,
        )

        cls.audio = cls.root / "audio.mka"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={cls.DURATION}",
            "-c:a", "libopus", str(cls.audio),
        ], check=True)

        cls.subtitle = cls.root / "subs.srt"
        cls.subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    @classmethod
    def _encode(cls, out_path: Path, *, crf: int, size: str | None = None, extra_vf: str | None = None) -> Path:
        # Real jw.org downloads always carry an embedded audio track; include one here too so
        # extract_audio_track's "fall back to the video file itself" path has something to copy.
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size or cls.SIZE}:rate={cls.RATE}:duration={cls.DURATION}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={cls.DURATION}",
        ]
        if extra_vf:
            cmd += ["-vf", extra_vf]
        cmd += [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-g", str(cls.GOP), "-c:a", "aac", "-shortest", str(out_path),
        ]
        subprocess.run(cmd, check=True)
        return out_path

    @classmethod
    def _encode_with_frozen_tail(cls, out_path: Path, *, live_s: int, freeze_s: int) -> Path:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={cls.SIZE}:rate={cls.RATE}:duration={live_s}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={live_s + freeze_s}",
            "-vf", f"tpad=stop_mode=clone:stop_duration={freeze_s}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-g", str(cls.GOP), "-c:a", "aac", "-shortest", str(out_path),
        ]
        subprocess.run(cmd, check=True)
        return out_path


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class AnalyzeVideoVariantsIntegrationTest(_FfmpegFixtureCase):
    def test_exact_equality_is_hash_matched_without_decoding(self) -> None:
        result = self.module.analyze_video_variants({"E": self.ref, "TG": self.same_bytes})
        self.assertEqual(result["comparisons"]["TG"]["classification"], "exactly_same")
        self.assertEqual(sorted(result["exact_groups"][0]), ["E", "TG"])

    def test_encoding_only_difference_is_visually_same_not_a_false_positive(self) -> None:
        # Same source content, same duration/rate/resolution, just a different CRF -- this is exactly
        # the "encoding bits differ, content doesn't" scenario that previously misclassified as different.
        result = self.module.analyze_video_variants({"E": self.ref, "TG": self.diff_encode})
        record = result["comparisons"]["TG"]
        self.assertNotEqual(
            self.module.elementary_video_hash(self.ref), self.module.elementary_video_hash(self.diff_encode),
        )
        self.assertEqual(record["classification"], "visually_same")
        self.assertEqual(record["intervals"], [])

    def test_one_localized_interval_is_detected_by_both_metrics(self) -> None:
        result = self.module.analyze_video_variants({"E": self.ref, "HV": self.localized})
        record = result["comparisons"]["HV"]
        self.assertEqual(record["classification"], "localized_candidates")
        self.assertEqual(len(record["intervals"]), 1)
        start, end = record["intervals"][0]
        # The overlay ran 2.3s-4.6s; allow slack for frame-boundary quantization at 15fps.
        self.assertLess(start, 2.6)
        self.assertGreater(end, 4.3)
        self.assertTrue(record["ssim_intervals"])
        self.assertTrue(record["psnr_intervals"])

    def test_globally_dissimilar_pair_is_review_recommended_not_visually_same(self) -> None:
        # A whole-clip (not windowed) semi-transparent overlay: every frame is moderately less similar,
        # so there's no sustained *deviation* from the pair's own median for candidate_intervals to catch
        # -- it IS the median. Without the median-similarity guard this silently passed as "visually_same".
        result = self.module.analyze_video_variants({"E": self.ref, "TG": self.globally_dissimilar})
        record = result["comparisons"]["TG"]
        self.assertLess(record["ssim_median"], 0.92)
        self.assertTrue(record["globally_uncertain"])
        self.assertEqual(record["classification"], "review_recommended")

    def test_incompatible_resolution_is_flagged_without_crashing(self) -> None:
        result = self.module.analyze_video_variants({"E": self.ref, "SA": self.incompatible})
        record = result["comparisons"]["SA"]
        self.assertFalse(record["compatible"])
        self.assertEqual(record["classification"], "incompatible")
        self.assertEqual(record["intervals"], [])

    def test_trailing_freeze_start_finds_the_held_frame(self) -> None:
        # 5s live + 1s frozen tail -> freeze should start right around t=5.
        freeze_at = self.module.trailing_freeze_start(self.tail_short, min_freeze_s=0.8)
        self.assertIsNotNone(freeze_at)
        self.assertAlmostEqual(freeze_at, 5.0, delta=0.3)

    def test_trailing_freeze_start_none_for_live_content(self) -> None:
        # self.ref never freezes (constant motion throughout) -- there's no trailing freeze to find.
        self.assertIsNone(self.module.trailing_freeze_start(self.ref, min_freeze_s=0.8))

    def test_duration_mismatch_becomes_compatible_via_shared_freeze_point(self) -> None:
        # tail_short (6s total) and tail_long (8s total) differ by 2s of raw duration -- past the 0.25s
        # tolerance -- but both freeze on the same live content at the same point (~t=5). This is
        # exactly the real "SCE Orientation" case: a duration mismatch that's just a differently-held
        # end card, not a real difference.
        result = self.module.analyze_video_variants({"E": self.tail_short, "TG": self.tail_long})
        record = result["comparisons"]["TG"]
        self.assertGreater(record["duration_delta"], 0.25)
        self.assertTrue(record["compatible"])
        self.assertIn("trailing_freeze_note", record)
        self.assertAlmostEqual(record["effective_duration"], 5.0, delta=0.3)
        # The live content is byte-for-byte identical between the two fixtures, so once compatible,
        # comparison should find nothing wrong.
        self.assertIn(record["classification"], ("exactly_same", "visually_same"))

    def test_duration_mismatch_without_shared_freeze_point_stays_incompatible(self) -> None:
        # tail_long freezes at ~t=5; tail_no_shared_freeze freezes at ~t=3 with a different total
        # duration too -- the freeze points themselves disagree, so this must NOT be forced compatible.
        result = self.module.analyze_video_variants({"E": self.tail_long, "TG": self.tail_no_shared_freeze})
        record = result["comparisons"]["TG"]
        self.assertFalse(record["compatible"])
        self.assertEqual(record["classification"], "incompatible")
        self.assertNotIn("trailing_freeze_note", record)

    def test_scan_small_regions_is_opt_in(self) -> None:
        result = self.module.analyze_video_variants({"E": self.ref, "HV": self.localized})
        self.assertNotIn("region_candidates", result["comparisons"]["HV"])

    def test_scan_small_regions_produces_well_formed_region_candidates(self) -> None:
        result = self.module.analyze_video_variants(
            {"E": self.ref, "HV": self.localized}, scan_small_regions=True, region_count=8,
        )
        record = result["comparisons"]["HV"]
        self.assertIn("region_candidates", record)
        for candidate in record["region_candidates"]:
            self.assertLess(candidate["start"], candidate["end"])
            self.assertTrue(candidate["strips"])
            self.assertTrue(all(0 <= s < 8 for s in candidate["strips"]))
            self.assertIn("psnr_corroborated", candidate)


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class KeyframeSnappingIntegrationTest(_FfmpegFixtureCase):
    def test_extract_video_segment_snaps_a_non_keyframe_request_outward(self) -> None:
        kf = self.module.keyframe_times(self.ref)
        self.assertIn(2.0, [round(t, 3) for t in kf])  # GOP=15 @ 15fps -> keyframe every 1s
        out_path = self.root / "snapped_segment.mkv"
        # Request a mid-GOP window; the caller never guarantees keyframe-aligned input.
        actual_start, actual_end = self.module.extract_video_segment(self.ref, 2.3, 3.7, out_path)
        self.assertTrue(out_path.exists())
        self.assertLessEqual(actual_start, 2.3)
        self.assertGreaterEqual(actual_end, 3.7)
        rounded_kf = {round(t, 2) for t in kf}
        self.assertIn(round(actual_start, 2), rounded_kf)

    def test_extract_video_segment_uses_passed_in_keyframes_without_rescanning(self) -> None:
        # build_adaptive_library scans each source file's keyframes once and reuses the list across
        # every segment cut from it (a real 79-minute/97-segment library previously spent over half its
        # runtime redundantly re-scanning the same few files). Passing a deliberately wrong keyframe
        # list here proves the function actually uses what it's given rather than recomputing.
        fake_keyframes = [0.0, 5.0]  # ref.mkv's real keyframes are every 1s (GOP=15@15fps); this is wrong
        out_path = self.root / "fake_keyframe_segment.mkv"
        actual_start, actual_end = self.module.extract_video_segment(
            self.ref, 2.3, 3.7, out_path, keyframes=fake_keyframes,
        )
        self.assertEqual(actual_start, 0.0)  # snapped to the fake list's 0.0, not the real ~2.0 keyframe
        self.assertEqual(actual_end, 5.0)
        self.assertTrue(out_path.exists())


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class AdaptiveLibraryIntegrationTest(_FfmpegFixtureCase):
    def test_build_adaptive_library_end_to_end(self) -> None:
        video_paths = {"E": self.ref, "HV": self.localized}
        variant_analysis = self.module.analyze_video_variants(video_paths)
        self.assertEqual(variant_analysis["comparisons"]["HV"]["classification"], "localized_candidates")

        local_files = {
            "E": {"video": self.ref, "audio": self.audio, "sub": self.subtitle},
            "HV": {"video": self.localized},  # no dedicated audio/sub files -- exercises the fallback + warning
        }
        library_dir = self.root / "adaptive-library"
        manifest = self.module.build_adaptive_library(
            reference="E", video_paths=video_paths, variant_analysis=variant_analysis,
            local_files=local_files, library_dir=library_dir, min_seconds=1.5,
        )

        self.assertTrue((library_dir / "manifest.json").exists())
        on_disk = json.loads((library_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["reference_language"], "E")

        kinds = {seg["kind"] for seg in manifest["segments"]}
        self.assertIn("common", kinds)
        self.assertIn("localized", kinds)
        for seg in manifest["segments"]:
            self.assertTrue((library_dir / seg["file"]).exists())

        self.assertIn("E", manifest["languages"])
        self.assertIn("HV", manifest["languages"])
        self.assertTrue((library_dir / manifest["languages"]["E"]["edl"]).exists())
        self.assertTrue((library_dir / manifest["languages"]["HV"]["edl"]).exists())
        # HV has no dedicated audio file, but its video (like any real jw.org download) carries
        # its own embedded audio track, so the fallback should still produce one.
        self.assertIsNotNone(manifest["languages"]["HV"]["audio"])
        self.assertTrue((library_dir / manifest["languages"]["HV"]["audio"]).exists())
        self.assertIsNone(manifest["languages"]["HV"]["subtitle"])
        self.assertTrue(any("No local subtitle found for language HV" in w for w in manifest["warnings"]))

        if MPV_AVAILABLE:
            for lang, verdict in manifest["validation"].items():
                self.assertTrue(verdict.get("ok"), f"mpv failed to validate {lang} presentation: {verdict}")
        else:
            for verdict in manifest["validation"].values():
                self.assertIn("skipped", verdict)

    def test_build_adaptive_library_skips_incompatible_languages(self) -> None:
        video_paths = {"E": self.ref, "HV": self.localized, "SA": self.incompatible}
        variant_analysis = self.module.analyze_video_variants(video_paths)
        local_files = {
            "E": {"video": self.ref, "audio": self.audio, "sub": self.subtitle},
            "HV": {"video": self.localized, "audio": self.audio, "sub": self.subtitle},
            "SA": {"video": self.incompatible},
        }
        manifest = self.module.build_adaptive_library(
            reference="E", video_paths=video_paths, variant_analysis=variant_analysis,
            local_files=local_files, library_dir=self.root / "adaptive-library-2", min_seconds=1.5,
        )
        self.assertEqual(manifest["incompatible_languages"], ["SA"])
        self.assertNotIn("SA", manifest["languages"])
        self.assertTrue(any("Skipped incompatible video languages" in w for w in manifest["warnings"]))

    def test_build_adaptive_library_warns_on_manual_override_resolution_mismatch(self) -> None:
        # A --manual-overrides entry can force a technically-incompatible (different resolution) pair
        # into localized_candidates -- e.g. a pillarboxed remaster confirmed as real content by a human.
        # mpv can play through the resulting resolution jump (verified against real footage), but the
        # library should say so rather than silently produce a presentation that visibly resizes mid-play.
        video_paths = {"E": self.ref, "SA": self.incompatible}
        variant_analysis = self.module.analyze_video_variants(video_paths)
        self.module.apply_manual_overrides(
            variant_analysis, {"languages": ["SA"], "differences": [{"start_s": 1.0, "end_s": 3.0, "label": "test"}]},
        )
        self.assertEqual(variant_analysis["comparisons"]["SA"]["classification"], "localized_candidates")
        local_files = {
            "E": {"video": self.ref, "audio": self.audio, "sub": self.subtitle},
            "SA": {"video": self.incompatible, "audio": self.audio},
        }
        manifest = self.module.build_adaptive_library(
            reference="E", video_paths=video_paths, variant_analysis=variant_analysis,
            local_files=local_files, library_dir=self.root / "adaptive-library-3", min_seconds=1.5,
        )
        self.assertTrue(any("different resolution than the reference" in w for w in manifest["warnings"]))

    def test_normalize_mismatched_aspect_crops_and_matches_reference_resolution(self) -> None:
        # Real-world case this models: an old 4:3 reference talk with a 16:9 localized title-card
        # insert -- mpv visibly resizes its window at that splice unless the mismatched clip is
        # cropped/scaled to the reference's own aspect ratio and resolution first.
        widescreen = self.root / "widescreen_localized.mkv"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=480x270:rate=15:duration=8",  # 16:9, vs. self.ref's 4:3
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-g", str(self.GOP), "-c:a", "aac", "-shortest", str(widescreen),
        ], check=True)

        video_paths = {"E": self.ref, "SA": widescreen}
        variant_analysis = self.module.analyze_video_variants(video_paths)
        self.module.apply_manual_overrides(
            variant_analysis, {"languages": ["SA"], "differences": [{"start_s": 1.0, "end_s": 3.0, "label": "test"}]},
        )
        self.assertEqual(variant_analysis["comparisons"]["SA"]["classification"], "localized_candidates")
        local_files = {
            "E": {"video": self.ref, "audio": self.audio, "sub": self.subtitle},
            "SA": {"video": widescreen, "audio": self.audio},
        }
        manifest = self.module.build_adaptive_library(
            reference="E", video_paths=video_paths, variant_analysis=variant_analysis,
            local_files=local_files, library_dir=self.root / "adaptive-library-aspect", min_seconds=1.5,
            normalize_mismatched_aspect=True,
        )
        self.assertTrue(any("center-cropped to the reference's aspect ratio" in w for w in manifest["warnings"]))
        self.assertFalse(any("will visibly resize" in w for w in manifest["warnings"]))

        localized_files = [s["file"] for s in manifest["segments"] if s["source_language"] == "SA"]
        self.assertTrue(localized_files, "expected at least one SA localized segment")
        for name in localized_files:
            profile = self.module.probe_video(self.root / "adaptive-library-aspect" / name)
            self.assertEqual(
                (profile["width"], profile["height"]), (self.ref_profile_dims()),
                f"{name} should have been cropped+scaled to the reference's exact resolution",
            )

    def ref_profile_dims(self) -> tuple[int, int]:
        profile = self.module.probe_video(self.ref)
        return (profile["width"], profile["height"])

    def test_coarse_keyframes_never_produce_overlapping_same_file_segments(self) -> None:
        # Reproduces a real incident (2026-07-29): on footage with a keyframe interval coarse relative
        # to segment length, independent per-segment keyframe expansion snapped a later common segment's
        # start BACK to before an earlier common segment's (already keyframe-expanded) end -- both cut
        # from the SAME reference file -- so playback of the reference language's own EDL (which should
        # have zero divergence from itself) visibly rewound/skipped at the splice. Build a reference with
        # a deliberately coarse GOP (keyframe roughly every 2.7s at 15fps) and a short (~1.6s) localized
        # window positioned so keyframe expansion of the surrounding common segments would previously
        # have overlapped.
        coarse_gop = 40  # ~2.67s between keyframes at 15fps
        ref = self.root / "coarse_ref.mkv"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={self.SIZE}:rate={self.RATE}:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-g", str(coarse_gop), "-c:a", "aac", "-shortest", str(ref),
        ], check=True)
        localized = self.root / "coarse_localized.mkv"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={self.SIZE}:rate={self.RATE}:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-vf", "drawbox=x=40:y=40:w=200:h=120:color=red@1.0:t=fill:enable='between(t,1.0,2.6)'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-g", str(coarse_gop), "-c:a", "aac", "-shortest", str(localized),
        ], check=True)

        video_paths = {"E": ref, "HV": localized}
        variant_analysis = self.module.analyze_video_variants(video_paths)
        self.assertEqual(variant_analysis["comparisons"]["HV"]["classification"], "localized_candidates")

        local_files = {"E": {"video": ref, "audio": self.audio}, "HV": {"video": localized}}
        library_dir = self.root / "coarse-adaptive-library"
        manifest = self.module.build_adaptive_library(
            reference="E", video_paths=video_paths, variant_analysis=variant_analysis,
            local_files=local_files, library_dir=library_dir, min_seconds=1.5,
        )

        self.assertGreater(
            manifest["reencoded_segments"], 0,
            "this fixture is specifically constructed to need the overlap-prevention fallback -- if "
            "nothing triggered it, the fixture (or the fix) needs a second look",
        )

        by_file: dict[str, list[dict]] = {}
        for seg in sorted(manifest["segments"], key=lambda s: s["index"]):
            by_file.setdefault(seg["source_language"], []).append(seg)
        for lang, segs in by_file.items():
            for prev, cur in zip(segs, segs[1:]):
                self.assertGreaterEqual(
                    cur["extracted_start"], prev["extracted_end"] - 1e-6,
                    f"{lang}: segment {cur['index']} ({cur['file']}) starts at {cur['extracted_start']} "
                    f"before the previous same-file segment {prev['file']} ends at {prev['extracted_end']} "
                    "-- this is exactly the overlap that caused visible rewind/skip during real playback",
                )


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class CleanupOnlyDeletesUsedFilesTest(unittest.TestCase):
    """Reproduces a real incident: --cleanup deleted source video for languages that were resolved by
    local-file-mode discovery (e.g. swept in via -s covering more languages than -v/-a) but never
    actually embedded in any output. Cleanup must only ever remove files it actually used."""

    JWVIDEOMUX = str(Path(__file__).resolve().parents[1] / "jwvideo-mux")

    def test_cleanup_spares_a_resolved_but_unused_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jwvideo-mux-cleanup-") as tmp:
            root = Path(tmp)
            tg_dir, e_dir = root / "TG", root / "E"
            tg_dir.mkdir()
            e_dir.mkdir()

            def make_clip(path: Path) -> None:
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path),
                ], check=True)

            anchor = tg_dir / "prefix_TG_test.mp4"
            make_clip(anchor)
            make_clip(e_dir / "prefix_E_test.mp4")  # resolved via sibling search, but E is never requested
            # Subtitle lookup for a sibling-discovered language sits next to that language's own
            # resolved video file (e_dir here), not next to the anchor -- a real bug found and fixed
            # 2026-07-29: it used to be directory-blind and looked in the anchor's own directory
            # instead, which silently missed every sidecar subtitle in a real SCE-layout library
            # (one directory per language).
            (e_dir / "prefix_E_test.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n", encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, self.JWVIDEOMUX, str(anchor), "-v", "TG", "-a", "TG", "-s", "TG,E",
                 "--cleanup", "--force"],
                cwd=root, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assertFalse(anchor.exists(), "TG's own video was embedded and should be cleaned up")
            self.assertFalse(
                (e_dir / "prefix_E_test.vtt").exists(), "E's subtitle was embedded and should be cleaned up",
            )
            self.assertTrue(
                (e_dir / "prefix_E_test.mp4").exists(),
                "E's video was resolved by discovery but never requested via -v/-a, and was never "
                "embedded in any output -- cleanup must not have touched it",
            )
            self.assertIn("Left", result.stdout)


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class LocalFileModeSrtSubtitleTest(unittest.TestCase):
    """Real SCE-layout sources use .srt sidecars, not .vtt (the jw.org API download format). Local-file
    mode's subtitle lookup must fall back to .srt when no .vtt sidecar exists, for both the anchor
    (base_lang) video and any sibling-discovered language -- otherwise every SCE library silently loses
    its subtitle tracks despite the .srt files sitting right there next to the videos."""

    JWVIDEOMUX = str(Path(__file__).resolve().parents[1] / "jwvideo-mux")

    def test_srt_sidecar_is_discovered_and_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jwvideo-mux-srt-") as tmp:
            root = Path(tmp)
            e_dir = root / "E"
            e_dir.mkdir()

            anchor = e_dir / "prefix_E_test.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(anchor),
            ], check=True)
            srt_path = anchor.with_suffix(".srt")
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, self.JWVIDEOMUX, str(anchor), "-v", "E", "-a", "E", "-s", "E",
                 "--cleanup", "--force"],
                cwd=root, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(
                srt_path.exists(), "the .srt sidecar should have been discovered, embedded, and cleaned up",
            )


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class VariantFlagsNeverFallThroughToMuxTest(unittest.TestCase):
    """Reproduces a second real incident: an ambiguous sibling-prefix match (two same-day talks whose
    filenames collide once the language token is stripped, e.g. "tscv_E_18..." and "tscv_E_19...") makes
    every other-language video unresolvable, dropping video_paths to 1. With --analyze-video-variants
    requested, the old code fell straight through the analysis gate into an ordinary mux and wrote a real
    output file nobody asked for -- confirmed live against actual SCE Media files, twice."""

    JWVIDEOMUX = str(Path(__file__).resolve().parents[1] / "jwvideo-mux")

    def test_ambiguous_sibling_prefix_stops_before_muxing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jwvideo-mux-noplan-") as tmp:
            root = Path(tmp)
            e_dir, tg_dir = root / "E", root / "TG"
            e_dir.mkdir()
            tg_dir.mkdir()

            def make_clip(path: Path) -> None:
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=1",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                    str(path),
                ], check=True)

            # No number right after the language code, so the numbered-disambiguation path (see
            # test_numbered_sibling_prefix_disambiguates_same_day_videos below) doesn't apply --
            # this falls back to the plain prefix, which both TG candidates below still match.
            anchor = e_dir / "talk_E_r720P.mp4"
            make_clip(anchor)
            # Both share the "talk" prefix once "_E_"/"_TG_" is stripped -- the sibling glob for TG
            # matches both, so len(candidates) != 1 and TG is left unresolved (not an error, just "not
            # found"). video_paths ends up with only E in it.
            make_clip(tg_dir / "talk_TG_partA_r720P.mp4")
            make_clip(tg_dir / "talk_TG_partB_r720P.mp4")

            result = subprocess.run(
                [sys.executable, self.JWVIDEOMUX, str(anchor), "-v", "E,TG", "-a", "NONE", "-s", "NONE",
                 "--analyze-video-variants"],
                cwd=root, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing to analyze", result.stdout)
            self.assertNotIn("Merged video created", result.stdout)
            self.assertEqual(list(e_dir.glob("*.mkv")), [], "no output file should have been written")
            self.assertEqual(list(root.glob("*.mkv")), [])

    def test_numbered_sibling_prefix_disambiguates_same_day_videos(self) -> None:
        # Real case: SCE Media's "5-2 Jehovah Never Freezes People" has tscv_E_18_... and
        # tscv_E_19_... anchors in the same folder, each with TG/HV/SA siblings named the same way.
        # The number right after the language code must stay part of the sibling glob, or (as above)
        # both "18" and "19" candidates match and neither resolves.
        with tempfile.TemporaryDirectory(prefix="jwvideo-mux-numbered-") as tmp:
            root = Path(tmp)
            e_dir, tg_dir = root / "E", root / "TG"
            e_dir.mkdir()
            tg_dir.mkdir()

            def make_clip(path: Path) -> None:
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=1",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                    str(path),
                ], check=True)

            anchor_18 = e_dir / "tscv_E_18_r720P.mp4"
            make_clip(anchor_18)
            make_clip(e_dir / "tscv_E_19_r720P.mp4")
            make_clip(tg_dir / "tscv_TG_18_r720P.mp4")
            make_clip(tg_dir / "tscv_TG_19_r720P.mp4")

            result = subprocess.run(
                [sys.executable, self.JWVIDEOMUX, str(anchor_18), "-v", "E,TG", "-a", "NONE", "-s", "NONE",
                 "--analyze-video-variants"],
                cwd=root, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            json_start = result.stdout.find("{")
            self.assertNotEqual(json_start, -1, result.stdout)
            analysis = json.loads(result.stdout[json_start:])
            self.assertIn("TG", analysis["comparisons"])


@unittest.skipUnless(FFMPEG_AVAILABLE and FFPROBE_AVAILABLE, "ffmpeg/ffprobe not installed")
class AdaptiveLibraryFallsBackWhenNothingLocalizedTest(unittest.TestCase):
    """Real-world case: several SCE videos (e.g. a plain workshop clip with no per-language visual
    differences at all) have nothing for --adaptive-mpv-library to actually split -- every language is
    exactly_same/visually_same. Building a whole EDL library (manifest, per-language audio/subs/EDL/
    launchers) for a presentation that's really just one video is needless ceremony. In that case
    jwvideo-mux should fall back to an ordinary single-file mux with one shared video track, written
    directly to the output directory -- no library subfolder, no EDL, no launchers."""

    JWVIDEOMUX = str(Path(__file__).resolve().parents[1] / "jwvideo-mux")

    def test_no_localized_differences_produces_single_mkv_not_a_library(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jwvideo-mux-fallback-") as tmp:
            root = Path(tmp)
            e_dir, tg_dir = root / "E", root / "TG"
            e_dir.mkdir()
            tg_dir.mkdir()

            def make_clip(path: Path, *, crf: int) -> None:
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
                ], check=True)

            anchor = e_dir / "prefix_E_test.mp4"
            make_clip(anchor, crf=20)
            # Different encode (crf), same visual content -- this is exactly "visually_same," the
            # ordinary case of the same footage encoded twice, not a real localized difference.
            make_clip(tg_dir / "prefix_TG_test.mp4", crf=28)

            result = subprocess.run(
                [sys.executable, self.JWVIDEOMUX, str(anchor), "-v", "E,TG", "-a", "E,TG", "-s", "NONE",
                 "-o", "..", "--adaptive-mpv-library", "--force"],
                cwd=e_dir, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing to adapt", result.stdout)

            no_library_dirs = [p for p in root.iterdir() if p.is_dir() and p.name not in ("E", "TG")]
            self.assertEqual(no_library_dirs, [], f"expected no library subfolder, found: {no_library_dirs}")

            mkvs = list(root.glob("*.mkv"))
            self.assertEqual(len(mkvs), 1, f"expected exactly one output MKV in {root}, found: {mkvs}")

            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index",
                 "-of", "csv=p=0", str(mkvs[0])],
                capture_output=True, text=True, check=True,
            )
            video_stream_count = len([l for l in probe.stdout.splitlines() if l.strip()])
            self.assertEqual(video_stream_count, 1, "expected exactly one shared video track, not one per language")


if __name__ == "__main__":
    unittest.main()
