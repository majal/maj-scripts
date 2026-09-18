from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support import REPO_ROOT, load_script_module


class FfcutTimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def test_time_to_seconds_plain(self) -> None:
        self.assertEqual(self.ffcut.time_to_seconds("10"), Decimal("10"))
        self.assertEqual(self.ffcut.time_to_seconds("10.25"), Decimal("10.25"))

    def test_time_to_seconds_mm_ss(self) -> None:
        self.assertEqual(self.ffcut.time_to_seconds("1:30"), Decimal("90"))

    def test_time_to_seconds_hh_mm_ss(self) -> None:
        self.assertEqual(self.ffcut.time_to_seconds("01:02:03.5"), Decimal("3723.5"))

    def test_time_to_seconds_negative(self) -> None:
        self.assertEqual(self.ffcut.time_to_seconds("-5"), Decimal("-5"))

    def test_time_to_seconds_rejects_too_many_parts(self) -> None:
        with self.assertRaises(ValueError):
            self.ffcut.time_to_seconds("1:02:03:04")

    def test_resolve_time_keywords(self) -> None:
        duration = Decimal("42")
        self.assertEqual(self.ffcut.resolve_time("start", duration), Decimal(0))
        self.assertEqual(self.ffcut.resolve_time("s", duration), Decimal(0))
        self.assertEqual(self.ffcut.resolve_time("end", duration), duration)
        self.assertEqual(self.ffcut.resolve_time("e", duration), duration)

    def test_resolve_time_negative_from_end(self) -> None:
        duration = Decimal("100")
        self.assertEqual(self.ffcut.resolve_time("-10", duration), Decimal("90"))

    def test_fmt_time_does_not_use_scientific_notation(self) -> None:
        # Regression test: str(Decimal) renders 0 as "0E-9" once quantized to
        # 9 places, which ffmpeg/ffprobe can't parse as a time argument.
        self.assertEqual(self.ffcut.fmt_time(Decimal(0)), "0.000000000")
        self.assertEqual(self.ffcut.fmt_time(Decimal("0.000000000")), "0.000000000")
        self.assertEqual(self.ffcut.fmt_time(Decimal("10.25")), "10.250000000")

    def test_flt_eq(self) -> None:
        self.assertTrue(self.ffcut.flt_eq(Decimal("1.0001"), Decimal("1.0004")))
        self.assertFalse(self.ffcut.flt_eq(Decimal("1.0001"), Decimal("1.002")))


class FfcutChaptersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def test_parse_and_trim_chapters(self) -> None:
        text = (
            ";FFMETADATA1\n"
            "[CHAPTER]\n"
            "TIMEBASE=1/1000\n"
            "START=0\n"
            "END=8000\n"
            "title=Chapter One\n"
            "[CHAPTER]\n"
            "TIMEBASE=1/1000\n"
            "START=8000\n"
            "END=20000\n"
            "title=Chapter Two\n"
        )
        chapters = self.ffcut.parse_ffmetadata_chapters(text)
        self.assertEqual(len(chapters), 2)

        trimmed = self.ffcut.trim_chapters(chapters, Decimal("3.234"), Decimal("12.876"))
        self.assertEqual(len(trimmed), 2)
        self.assertEqual(trimmed[0].start, Decimal("0"))
        self.assertEqual(trimmed[0].end, Decimal("4766"))
        self.assertEqual(trimmed[1].start, Decimal("4766"))
        self.assertEqual(trimmed[1].end, Decimal("9642"))
        self.assertEqual(trimmed[0].tags, ["title=Chapter One"])

    def test_trim_chapters_drops_chapters_outside_range(self) -> None:
        chapters = [self.ffcut.ChapterBlock("1/1000", Decimal(0), Decimal(1000), [])]
        trimmed = self.ffcut.trim_chapters(chapters, Decimal("5"), Decimal("10"))
        self.assertEqual(trimmed, [])

    def test_render_ffmetadata_chapters_roundtrip(self) -> None:
        chapters = [self.ffcut.ChapterBlock("1/1000", Decimal(0), Decimal(4766), ["title=Chapter One"])]
        rendered = self.ffcut.render_ffmetadata_chapters(chapters)
        reparsed = self.ffcut.parse_ffmetadata_chapters(rendered)
        self.assertEqual(len(reparsed), 1)
        self.assertEqual(reparsed[0].start, Decimal(0))
        self.assertEqual(reparsed[0].end, Decimal(4766))


class FfcutCodecProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")
        cls.opts = cls.ffcut.build_arg_parser().parse_args(["in.mp4", "0", "1"])

    def test_h264_is_smart_capable(self) -> None:
        profile = self.ffcut.build_codec_profile("h264", self.opts)
        self.assertTrue(profile.smart_capable)
        self.assertEqual(profile.encoder, "libx264")
        self.assertIn("-crf", profile.enc_args)

    def test_hevc_uses_closed_gop_params(self) -> None:
        profile = self.ffcut.build_codec_profile("hevc", self.opts)
        self.assertTrue(profile.smart_capable)
        self.assertIn("open-gop=0:repeat-headers=1", profile.enc_args)

    def test_mpeg2_is_not_smart_capable(self) -> None:
        profile = self.ffcut.build_codec_profile("mpeg2video", self.opts)
        self.assertFalse(profile.smart_capable)

    def test_unsupported_codec_raises(self) -> None:
        with self.assertRaises(self.ffcut.FfcutError):
            self.ffcut.build_codec_profile("not_a_real_codec", self.opts)

    def test_custom_crf_flag_is_applied(self) -> None:
        opts = self.ffcut.build_arg_parser().parse_args(["in.mp4", "0", "1", "--h264-crf", "5"])
        profile = self.ffcut.build_codec_profile("h264", opts)
        self.assertIn("5", profile.enc_args)


class FfcutProbeHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def _probe(self, streams: list[dict]) -> dict:
        return {"streams": streams, "format": {}}

    def test_data_stream_indexes_excludes_chapter_track(self) -> None:
        probe = self._probe([
            {
                "index": 2,
                "codec_type": "data",
                "codec_name": "bin_data",
                "codec_tag_string": "text",
                "tags": {"handler_name": "SubtitleHandler"},
            },
            {
                "index": 5,
                "codec_type": "data",
                "codec_name": "bin_data",
                "codec_tag_string": "gpmd",
                "tags": {"handler_name": "SubtitleHandler"},
            },
        ])
        self.assertEqual(self.ffcut.data_stream_indexes_to_copy(probe), [5])
        self.assertEqual(self.ffcut.nonchapter_data_count(probe), 1)

    def test_cover_streams_and_codec_list(self) -> None:
        probe = self._probe([
            {"index": 0, "codec_type": "video", "codec_name": "h264", "disposition": {"attached_pic": 0}},
            {"index": 3, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ])
        covers = self.ffcut.cover_streams(probe)
        self.assertEqual([s["index"] for s in covers], [3])
        self.assertEqual(self.ffcut.cover_codec_list(probe), ["mjpeg"])

    def test_audio_and_subtitle_codec_lists_are_sorted(self) -> None:
        probe = self._probe([
            {"index": 1, "codec_type": "audio", "codec_name": "opus"},
            {"index": 2, "codec_type": "audio", "codec_name": "aac"},
            {"index": 3, "codec_type": "subtitle", "codec_name": "mov_text"},
        ])
        self.assertEqual(self.ffcut.audio_codec_list(probe), ["aac", "opus"])
        self.assertEqual(self.ffcut.subtitle_codec_list(probe), ["mov_text"])

    def test_video_rotation_reads_display_matrix_side_data(self) -> None:
        stream = {"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]}
        self.assertEqual(self.ffcut.video_rotation(stream), Decimal("-90"))

    def test_video_rotation_defaults_to_zero(self) -> None:
        self.assertEqual(self.ffcut.video_rotation({}), Decimal(0))


class FfcutMuxCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def _ctx(self, **overrides):
        opts = self.ffcut.build_arg_parser().parse_args(["in.mp4", "0", "1"])
        profile = self.ffcut.build_codec_profile("h264", opts)
        defaults = dict(
            input=Path("in.mp4"),
            codec="h264",
            profile=profile,
            smart_capable=True,
            video_props=[],
            src_duration=Decimal("20"),
            src_start_time=Decimal(0),
            v_index=0,
            codec_tag="avc1",
            time_base="1/15360",
            rotation=Decimal(0),
        )
        defaults.update(overrides)
        return self.ffcut.Context(**defaults)

    def test_mp4_output_gets_tag_and_faststart(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
        )
        self.assertIn("-movflags", cmd)
        self.assertIn("+faststart", cmd)
        self.assertIn("-tag:v:0", cmd)
        self.assertIn("avc1", cmd)
        self.assertIn("-video_track_timescale", cmd)
        self.assertIn("15360", cmd)

    def test_mkv_output_gets_infer_no_subs(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.mkv"), Decimal("1"), Decimal("5"), None, "mkv", Path("final.mkv"),
        )
        self.assertIn("-default_mode", cmd)
        self.assertIn("infer_no_subs", cmd)
        self.assertNotIn("-movflags", cmd)

    def test_chapters_meta_sets_map_chapters_to_third_extra_input(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"),
            Path("chapters.ffmeta"), "mkv", Path("final.mkv"),
        )
        idx = cmd.index("-map_chapters")
        self.assertEqual(cmd[idx + 1], "3")

    def test_no_chapters_meta_disables_chapters(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mkv", Path("final.mkv"),
        )
        idx = cmd.index("-map_chapters")
        self.assertEqual(cmd[idx + 1], "-1")

    def test_cover_streams_get_attached_pic_disposition(self) -> None:
        ctx = self._ctx()
        probe = {"streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "disposition": {"attached_pic": 0}},
            {"index": 3, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ]}
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, probe, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
        )
        self.assertIn("-map", cmd)
        self.assertIn("2:3", cmd)
        self.assertIn("-disposition:v:1", cmd)
        self.assertIn("attached_pic", cmd)

    def test_rotation_sets_display_rotation_on_hybrid_input(self) -> None:
        ctx = self._ctx(rotation=Decimal("90"))
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
        )
        idx = cmd.index("-display_rotation:v:0")
        self.assertEqual(cmd[idx + 1], "90")

    def test_no_drop_opts_maps_everything(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
        )
        self.assertIn("1:a?", cmd)
        self.assertIn("1:s?", cmd)
        self.assertIn("2:t?", cmd)

    def test_drop_audio_omits_audio_map(self) -> None:
        ctx = self._ctx()
        drop = self.ffcut.DropOpts(audio=True)
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"), drop,
        )
        self.assertNotIn("1:a?", cmd)
        self.assertIn("1:s?", cmd)

    def test_drop_subs_omits_subtitle_map(self) -> None:
        ctx = self._ctx()
        drop = self.ffcut.DropOpts(subs=True)
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"), drop,
        )
        self.assertIn("1:a?", cmd)
        self.assertNotIn("1:s?", cmd)

    def test_drop_data_omits_data_stream_maps(self) -> None:
        ctx = self._ctx()
        probe = {"streams": [{"index": 5, "codec_type": "data", "codec_name": "bin_data"}]}
        drop = self.ffcut.DropOpts(data=True)
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, probe, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"), drop,
        )
        self.assertNotIn("1:5", cmd)

    def test_drop_cover_omits_cover_map_and_disposition(self) -> None:
        ctx = self._ctx()
        probe = {"streams": [
            {"index": 3, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ]}
        drop = self.ffcut.DropOpts(cover=True)
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, probe, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"), drop,
        )
        self.assertNotIn("2:3", cmd)
        self.assertNotIn("-disposition:v:1", cmd)

    def test_drop_attachments_omits_attachment_map(self) -> None:
        ctx = self._ctx()
        drop = self.ffcut.DropOpts(attachments=True)
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"), drop,
        )
        self.assertNotIn("2:t?", cmd)


class FfcutNoVideoMuxCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def test_no_video_maps_audio_subs_data_no_video(self) -> None:
        probe = {"streams": [{"index": 5, "codec_type": "data", "codec_name": "bin_data"}]}
        drop = self.ffcut.DropOpts()
        cmd = self.ffcut.build_no_video_mux_cmd(
            Path("in.mp4"), probe, Decimal("1"), Decimal("5"), None, "mkv", Path("final.mkv"), drop,
        )
        self.assertNotIn("0:v", cmd)
        self.assertIn("0:a?", cmd)
        self.assertIn("0:s?", cmd)
        self.assertIn("0:5", cmd)
        self.assertIn("1:t?", cmd)
        self.assertIn("-t", cmd)
        self.assertEqual(cmd[cmd.index("-t") + 1], "5.000000000")

    def test_no_video_respects_drop_flags(self) -> None:
        drop = self.ffcut.DropOpts(audio=True, subs=True, attachments=True)
        cmd = self.ffcut.build_no_video_mux_cmd(
            Path("in.mp4"), {"streams": []}, Decimal("1"), Decimal("5"), None, "mkv", Path("final.mkv"), drop,
        )
        self.assertNotIn("0:a?", cmd)
        self.assertNotIn("0:s?", cmd)
        self.assertNotIn("1:t?", cmd)

    def test_no_video_chapters_meta_sets_map_chapters_to_second_extra_input(self) -> None:
        drop = self.ffcut.DropOpts()
        cmd = self.ffcut.build_no_video_mux_cmd(
            Path("in.mp4"), {"streams": []}, Decimal("1"), Decimal("5"),
            Path("chapters.ffmeta"), "mkv", Path("final.mkv"), drop,
        )
        idx = cmd.index("-map_chapters")
        self.assertEqual(cmd[idx + 1], "2")

    def test_no_video_mp4_ext_gets_faststart(self) -> None:
        drop = self.ffcut.DropOpts()
        cmd = self.ffcut.build_no_video_mux_cmd(
            Path("in.mp4"), {"streams": []}, Decimal("1"), Decimal("5"), None, "m4a", Path("final.m4a"), drop,
        )
        self.assertIn("-movflags", cmd)
        self.assertIn("+faststart", cmd)


class FfcutVerifyAuxStreamsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def _opts(self, **overrides):
        opts = self.ffcut.build_arg_parser().parse_args(["in.mp4", "0", "1"])
        for key, value in overrides.items():
            setattr(opts, key, value)
        return opts

    def test_passes_when_nothing_dropped_and_nothing_changed(self) -> None:
        probe = {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
        self.ffcut.verify_aux_streams(self._opts(), probe, probe)

    def test_dies_when_no_audio_requested_but_audio_survives(self) -> None:
        input_probe = {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
        output_probe = {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
        with self.assertRaises(self.ffcut.FfcutError):
            self.ffcut.verify_aux_streams(self._opts(no_audio=True), input_probe, output_probe)

    def test_dies_when_audio_lost_unexpectedly(self) -> None:
        input_probe = {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
        output_probe = {"streams": []}
        with self.assertRaises(self.ffcut.FfcutError):
            self.ffcut.verify_aux_streams(self._opts(), input_probe, output_probe)

    def test_no_video_implies_cover_must_be_gone(self) -> None:
        input_probe = {"streams": [
            {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ]}
        output_probe = {"streams": [
            {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ]}
        with self.assertRaises(self.ffcut.FfcutError):
            self.ffcut.verify_aux_streams(self._opts(no_video=True), input_probe, output_probe)


class FfcutMiscTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def test_default_output_path(self) -> None:
        result = self.ffcut.default_output_path(Path("/videos/clip.mp4"))
        self.assertEqual(result, Path("/videos/clip - cut.mp4"))

    def test_default_output_path_no_extension(self) -> None:
        result = self.ffcut.default_output_path(Path("/videos/clip"))
        self.assertEqual(result, Path("/videos/clip - cut.mkv"))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not available")
class FfcutSmokeTest(unittest.TestCase):
    """End-to-end run against a tiny synthetic H.264 clip. Slow-ish but the
    clip is short (4s, 160x90) so it stays fast in CI."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.tmp_path = Path(cls.tmp.name)
        cls.source = cls.tmp_path / "src.mp4"

        srt_path = cls.tmp_path / "src.srt"
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nHello\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nWorld\n",
            encoding="utf-8",
        )
        chapters_path = cls.tmp_path / "src.ffmeta"
        chapters_path.write_text(
            ";FFMETADATA1\n"
            "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Intro\n"
            "[CHAPTER]\nTIMEBASE=1/1000\nSTART=2000\nEND=4000\ntitle=Outro\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=25:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                "-i", str(srt_path),
                "-i", str(chapters_path),
                "-map", "0:v", "-map", "1:a", "-map", "2:s",
                "-map_metadata", "3", "-map_chapters", "3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "25", "-crf", "30", "-preset", "ultrafast",
                "-c:a", "aac",
                "-c:s", "mov_text",
                str(cls.source),
            ],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_ffcut(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "ffcut"), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_help(self) -> None:
        result = self.run_ffcut("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_cut_produces_playable_output_with_correct_duration(self) -> None:
        out = self.tmp_path / "out.mp4"
        result = self.run_ffcut(str(self.source), "1.2", "3.1", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        self.assertAlmostEqual(duration, 1.9, delta=0.3)

        decode = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(out), "-f", "null", "-"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(decode.returncode, 0, decode.stderr)

    def test_no_audio_drops_audio_stream(self) -> None:
        out = self.tmp_path / "out-no-audio.mp4"
        result = self.run_ffcut(str(self.source), "1.2", "3.1", "--no-audio", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        codec_types = [s["codec_type"] for s in json.loads(probe.stdout)["streams"]]
        self.assertNotIn("audio", codec_types)
        self.assertIn("video", codec_types)

    def test_no_subs_drops_subtitle_stream(self) -> None:
        out = self.tmp_path / "out-no-subs.mp4"
        result = self.run_ffcut(str(self.source), "1.2", "3.1", "--no-subs", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        codec_types = [s["codec_type"] for s in json.loads(probe.stdout)["streams"]]
        self.assertNotIn("subtitle", codec_types)
        self.assertIn("video", codec_types)
        self.assertIn("audio", codec_types)

    def test_no_chapters_drops_chapters(self) -> None:
        out = self.tmp_path / "out-no-chapters.mp4"
        result = self.run_ffcut(str(self.source), "0", "end", "--no-chapters", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(probe.stdout).get("chapters"), [])

    def test_chapters_are_kept_by_default(self) -> None:
        out = self.tmp_path / "out-with-chapters.mp4"
        result = self.run_ffcut(str(self.source), "0", "end", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        self.assertTrue(json.loads(probe.stdout).get("chapters"))

    def test_no_video_extracts_audio_only(self) -> None:
        out = self.tmp_path / "out-audio-only.m4a"
        result = self.run_ffcut(str(self.source), "1.2", "3.1", "--no-video", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(probe.stdout)
        codec_types = [s["codec_type"] for s in data["streams"]]
        self.assertNotIn("video", codec_types)
        self.assertIn("audio", codec_types)
        duration = float(data["format"]["duration"])
        self.assertAlmostEqual(duration, 1.9, delta=0.3)

    def test_no_video_short_flag_matches_long_flag(self) -> None:
        out = self.tmp_path / "out-audio-only-short.m4a"
        result = self.run_ffcut(str(self.source), "1.2", "3.1", "-vn", "--no-play", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())

    def test_no_video_with_all_aux_streams_dropped_is_rejected(self) -> None:
        out = self.tmp_path / "out-empty.mka"
        result = self.run_ffcut(
            str(self.source), "1.2", "3.1", "--no-video", "--no-audio", "--no-subs", "--no-data",
            "--no-play", str(out),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nothing to cut", result.stderr)

    def test_end_must_be_after_start(self) -> None:
        out = self.tmp_path / "bad.mp4"
        result = self.run_ffcut(str(self.source), "3", "1", "--no-play", str(out))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("End must be after start", result.stderr)

    def test_refuses_to_overwrite_without_force(self) -> None:
        out = self.tmp_path / "exists.mp4"
        out.write_bytes(b"not a real video")
        result = self.run_ffcut(str(self.source), "0", "1", "--no-play", str(out))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--force", result.stderr)


if __name__ == "__main__":
    unittest.main()
