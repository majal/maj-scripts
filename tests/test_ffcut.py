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

    def test_video_offset_delays_only_the_video_input(self) -> None:
        ctx = self._ctx()
        cmd = self.ffcut.build_final_mux_cmd(
            ctx, {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
            video_offset=Decimal("0.02"),
        )
        i = cmd.index("-itsoffset")
        self.assertEqual(cmd[i + 1], "0.020000000")
        self.assertEqual(cmd[i + 2:i + 4], ["-i", "hybrid.ts"])
        self.assertEqual(cmd.count("-itsoffset"), 1)

    def test_no_video_offset_adds_no_itsoffset(self) -> None:
        cmd = self.ffcut.build_final_mux_cmd(
            self._ctx(), {"streams": []}, Path("hybrid.ts"), Decimal("1"), Decimal("5"), None, "mp4", Path("final.mp4"),
        )
        self.assertNotIn("-itsoffset", cmd)

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
        self.assertEqual(result, Path("/videos/clip_ffcut.mp4"))

    def test_default_output_path_no_extension(self) -> None:
        result = self.ffcut.default_output_path(Path("/videos/clip"))
        self.assertEqual(result, Path("/videos/clip_ffcut.mkv"))


class FfcutFrameBoundaryTest(unittest.TestCase):
    """Cut boundaries sit midway between frames so 6-decimal timestamp rounding
    and ffmpeg's own comparisons can't keep, drop or duplicate a boundary frame."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def ctx_with_frames(self, times):
        from unittest import mock
        ctx = mock.Mock(src_start_time=Decimal(0))
        patcher = mock.patch.object(self.ffcut, "frame_times", return_value=[Decimal(t) for t in times])
        patcher.start()
        self.addCleanup(patcher.stop)
        return ctx

    def test_boundary_is_midway_between_the_frames_either_side(self) -> None:
        ctx = self.ctx_with_frames(["1.00", "1.04", "1.08", "1.12"])
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("1.08")), Decimal("1.06"))
        # a time a hair before a frame still counts as that frame (typed-in frame time)
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("1.0799")), Decimal("1.06"))
        # a time inside a frame's span belongs to the NEXT frame: [start, end) semantics
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("1.07")), Decimal("1.06"))

    def test_boundary_before_first_and_after_last_frame(self) -> None:
        ctx = self.ctx_with_frames(["1.00", "1.04", "1.08"])
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("0.5")), Decimal("0.98"))
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("5")), Decimal("1.10"))

    def test_boundary_falls_back_when_frame_times_are_unreadable(self) -> None:
        ctx = self.ctx_with_frames([])
        self.assertEqual(self.ffcut.frame_boundary(ctx, Decimal("2")), Decimal("2") - self.ffcut.EQ_EPSILON)

    def test_frames_in_window_is_half_open(self) -> None:
        ctx = self.ctx_with_frames(["1.00", "1.04", "1.08", "1.12"])
        window = lambda a, b: self.ffcut.frames_in_window(ctx, Decimal(a), Decimal(b))
        self.assertEqual(window("1.04", "1.12"), [Decimal("1.04"), Decimal("1.08")])
        self.assertEqual(window("1.01", "1.03"), [])  # narrower than a frame, none inside
        self.assertEqual(window("1.03", "1.05"), [Decimal("1.04")])

    def test_frames_in_window_is_none_when_unreadable(self) -> None:
        ctx = self.ctx_with_frames([])
        self.assertIsNone(self.ffcut.frames_in_window(ctx, Decimal("1"), Decimal("2")))


class FfcutStartSyncTest(unittest.TestCase):
    """The video begins on the first whole frame at/after START; --start-sync picks
    how the rest of the streams are lined up with that."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def resolve(self, mode, frames, start="1.01", end="2"):
        from unittest import mock
        with mock.patch.object(self.ffcut, "frames_in_window", return_value=frames):
            return self.ffcut.resolve_start_sync(mock.Mock(), mode, Decimal(start), Decimal(end))

    def test_default_is_frame(self) -> None:
        opts = self.ffcut.build_arg_parser().parse_args(["in.mp4", "0", "1"])
        self.assertEqual(opts.start_sync, "frame")

    def test_frame_cuts_the_other_streams_at_the_first_frame(self) -> None:
        self.assertEqual(self.resolve("frame", [Decimal("1.04")]), (Decimal("1.04"), Decimal(0)))

    def test_audio_keeps_start_and_delays_the_video_by_the_gap(self) -> None:
        self.assertEqual(self.resolve("audio", [Decimal("1.04")]), (Decimal("1.01"), Decimal("0.03")))

    def test_off_changes_nothing(self) -> None:
        self.assertEqual(self.resolve("off", [Decimal("1.04")]), (Decimal("1.01"), Decimal(0)))

    def test_no_gap_when_start_is_on_a_frame(self) -> None:
        for mode in ("frame", "audio", "off"):
            self.assertEqual(self.resolve(mode, [Decimal("1.01")]), (Decimal("1.01"), Decimal(0)))

    def test_unreadable_or_empty_frame_times_mean_no_correction(self) -> None:
        for frames in (None, []):
            for mode in ("frame", "audio"):
                self.assertEqual(self.resolve(mode, frames), (Decimal("1.01"), Decimal(0)))

    def test_a_frame_slightly_before_start_is_not_a_negative_gap(self) -> None:
        self.assertEqual(self.resolve("audio", [Decimal("1.0098")]), (Decimal("1.01"), Decimal(0)))


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

    def source_frame_times(self) -> list[float]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(self.source)],
            capture_output=True, text=True, check=True,
        )
        return sorted(float(line.strip(",")) for line in probe.stdout.split() if line)

    def assert_cut_has_exactly_the_frames_in(self, start: str, end: str) -> None:
        out = self.tmp_path / "frames.mp4"
        out.unlink(missing_ok=True)
        result = self.run_ffcut(str(self.source), start, end, "--no-play", "--no-audio", "--no-subs", "--provenance", "none", str(out))
        self.assertEqual(result.returncode, 0, f"{start}-{end}: {result.stderr}")
        expected = [t for t in self.source_frame_times() if float(start) - 0.0005 <= t < float(end) - 0.0005]
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True,
        )
        got = sorted(float(line.strip(",")) for line in probe.stdout.split() if line)
        self.assertEqual(len(got), len(expected), f"{start}-{end}: frame count")
        gaps = [round(b - a, 3) for a, b in zip(got, got[1:])]
        self.assertTrue(all(abs(gap - 0.04) < 0.003 for gap in gaps), f"{start}-{end}: irregular frame spacing {gaps}")

    def test_start_between_the_last_frame_before_a_keyframe_and_the_keyframe(self) -> None:
        # Keyframes are at 1.0, 2.0, 3.0; the frame before the 1.0 one is at 0.96. A start
        # in (0.96, 1.0) has no whole frame before the first splice point: the head is
        # empty, which used to crash the join ("Invalid data found when processing input").
        for start in ("0.97", "0.99", "0.999", "1.5", "1.99"):
            with self.subTest(start=start):
                self.assert_cut_has_exactly_the_frames_in(start, "3.5")

    def test_start_just_before_a_frame_keeps_that_frame_and_no_extra(self) -> None:
        # A one-frame head: the exact count (not ffmpeg's own -t guess) decides it.
        for start in ("0.95", "0.9601", "1.4", "1.42"):
            with self.subTest(start=start):
                self.assert_cut_has_exactly_the_frames_in(start, "3.5")

    def test_end_on_or_near_a_frame_never_duplicates_the_seam_frame(self) -> None:
        # The copied middle ends and the re-encoded tail begins on the same keyframe; both
        # used to contain it when the keyframe's rounded timestamp compared a hair high.
        for end in ("2.0", "2.001", "2.01", "2.04", "2.5", "3.0", "3.96"):
            with self.subTest(end=end):
                self.assert_cut_has_exactly_the_frames_in("0.5", end)

    def stream_start_times(self, path: Path) -> dict[str, float]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time", "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        )
        return {s["codec_type"]: float(s["start_time"]) for s in json.loads(probe.stdout)["streams"]}

    def test_start_sync_modes_line_up_audio_and_video_as_documented(self) -> None:
        # 25fps, so frames are 0.04s apart: START 1.51 puts the first whole frame at 1.52,
        # a 10ms gap. Frame start times are checked as the offset between the two streams.
        results = {}
        for mode in ("off", "audio", "frame"):
            out = self.tmp_path / f"sync_{mode}.mp4"
            out.unlink(missing_ok=True)
            result = self.run_ffcut(str(self.source), "1.51", "3.0", "--no-play", "--no-subs", "--provenance", "none",
                                    "--start-sync", mode, str(out))
            self.assertEqual(result.returncode, 0, f"{mode}: {result.stderr}")
            starts = self.stream_start_times(out)
            results[mode] = starts["video"] - starts["audio"]
        # frame: both begin together (within one audio packet); off: video runs early by the gap
        self.assertAlmostEqual(results["frame"], 0, delta=0.025)
        self.assertAlmostEqual(results["audio"] - results["off"], 0.01, delta=0.003)
        self.assertGreater(results["audio"], results["off"])

    def test_start_sync_frame_shortens_the_cut_by_the_gap_only(self) -> None:
        out = self.tmp_path / "sync_len.mp4"
        out.unlink(missing_ok=True)
        result = self.run_ffcut(str(self.source), "1.51", "3.0", "--no-play", "--no-subs", "--provenance", "none", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True,
        )
        self.assertAlmostEqual(float(probe.stdout.strip(",\n ")), 1.48, delta=0.04)

    def test_window_with_no_safe_keyframe_inside_it(self) -> None:
        for start, end in (("1.1", "1.3"), ("1.01", "1.05"), ("1.2", "1.21")):
            with self.subTest(start=start, end=end):
                self.assert_cut_has_exactly_the_frames_in(start, end)


class FfcutStreamMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    probe = {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}, {"codec_type": "audio"}, {"codec_type": "subtitle"}]}

    def test_each_kept_audio_and_subtitle_stream_gets_its_tags_mapped(self) -> None:
        args = self.ffcut.passthrough_stream_metadata(self.probe, 1, self.ffcut.DropOpts())
        self.assertEqual(args, [
            "-map_metadata:s:a:0", "1:s:a:0", "-map_metadata:s:a:1", "1:s:a:1", "-map_metadata:s:s:0", "1:s:s:0",
        ])

    def test_dropped_stream_kinds_are_skipped(self) -> None:
        args = self.ffcut.passthrough_stream_metadata(self.probe, 0, self.ffcut.DropOpts(audio=True))
        self.assertEqual(args, ["-map_metadata:s:s:0", "0:s:s:0"])


class FfcutProvenanceHookTest(unittest.TestCase):
    """If jwkit's `jwkit-provenance` is installed, ffcut records the cut; if not, nothing happens."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ffcut = load_script_module("ffcut")

    def opts(self, argv, **overrides):
        opts = self.ffcut.build_arg_parser().parse_args(argv)
        opts._argv = argv
        for key, value in overrides.items():
            setattr(opts, key, value)
        return opts

    def test_records_source_window_command_and_settings(self) -> None:
        from unittest import mock
        argv = ["in.mp4", "10", "20", "--no-audio", "--provenance", "beside"]
        with mock.patch.object(self.ffcut, "find_jwkit_provenance", return_value="/x/jwkit-provenance"), \
             mock.patch.object(self.ffcut.subprocess, "run") as run:
            self.ffcut.record_provenance(self.opts(argv), Path("in.mp4"), Path("out.mp4"), Decimal("10"), Decimal("20"), video_codec="h264", smart_cut=True)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["/x/jwkit-provenance", "record", "out.mp4"])
        self.assertEqual(cmd[cmd.index("--tool") + 1], "ffcut")
        self.assertEqual(cmd[cmd.index("--source") + 1], "in.mp4")
        self.assertEqual(cmd[cmd.index("--window") + 1], "10.000000000-20.000000000")
        self.assertEqual(cmd[cmd.index("--command") + 1], "ffcut in.mp4 10 20 --no-audio --provenance beside")
        self.assertEqual(cmd[cmd.index("--provenance") + 1], "beside")
        settings = json.loads(cmd[cmd.index("--settings-json") + 1])
        self.assertEqual((settings["video_codec"], settings["smart_cut"], settings["no_audio"]), ("h264", True, True))

    def test_does_nothing_when_jwkit_is_not_installed(self) -> None:
        from unittest import mock
        with mock.patch.object(self.ffcut, "find_jwkit_provenance", return_value=None), mock.patch.object(self.ffcut.subprocess, "run") as run:
            self.ffcut.record_provenance(self.opts(["in.mp4", "1", "2"]), Path("in.mp4"), Path("out.mp4"), Decimal("1"), Decimal("2"))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
