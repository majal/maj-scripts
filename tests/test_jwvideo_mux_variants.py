from __future__ import annotations

import json
import shutil
import subprocess
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
            # Local-file mode's subtitle lookup is directory-blind (looks next to the anchor file), so
            # this is where the code actually looks for E's subtitle -- not in the E/ sibling directory.
            (tg_dir / "prefix_E_test.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n", encoding="utf-8",
            )

            result = subprocess.run(
                [self.JWVIDEOMUX, str(anchor), "-v", "TG", "-a", "TG", "-s", "TG,E", "--cleanup", "--force"],
                cwd=root, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assertFalse(anchor.exists(), "TG's own video was embedded and should be cleaned up")
            self.assertFalse(
                (tg_dir / "prefix_E_test.vtt").exists(), "E's subtitle was embedded and should be cleaned up",
            )
            self.assertTrue(
                (e_dir / "prefix_E_test.mp4").exists(),
                "E's video was resolved by discovery but never requested via -v/-a, and was never "
                "embedded in any output -- cleanup must not have touched it",
            )
            self.assertIn("Left", result.stdout)


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

            anchor = e_dir / "talk_E_18_r720P.mp4"
            make_clip(anchor)
            # Both share the "talk" prefix once "_E_"/"_TG_" is stripped -- the sibling glob for TG
            # matches both, so len(candidates) != 1 and TG is left unresolved (not an error, just "not
            # found"). video_paths ends up with only E in it.
            make_clip(tg_dir / "talk_TG_18_r720P.mp4")
            make_clip(tg_dir / "talk_TG_19_r720P.mp4")

            result = subprocess.run(
                [self.JWVIDEOMUX, str(anchor), "-v", "E,TG", "-a", "NONE", "-s", "NONE",
                 "--analyze-video-variants"],
                cwd=root, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing to analyze", result.stdout)
            self.assertNotIn("Merged video created", result.stdout)
            self.assertEqual(list(e_dir.glob("*.mkv")), [], "no output file should have been written")
            self.assertEqual(list(root.glob("*.mkv")), [])


if __name__ == "__main__":
    unittest.main()
