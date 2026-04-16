from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support import load_script_module


class WhisperOutputPlanningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.whisper = load_script_module("whisper")

    def test_build_processing_env_sets_expected_flags(self) -> None:
        args = argparse.Namespace(
            targets=["clip.mp4"],
            lang="en",
            jobs=3,
            outdir="/tmp/out",
            bible_reference_normalization=True,
            bible_reference_phrases=True,
            speech_trim=False,
            review_postprocessing=True,
            subtitle_style="strict",
            glossary=["/tmp/glossary.txt"],
            suppress_phrases=["/tmp/suppress.txt"],
            recursive=True,
            ass=True,
            embed=False,
            embed_file="captions.srt",
            in_place=True,
            burn=False,
            burn_vcodec="libx264",
            font="Aptos",
            karaoke=True,
        )

        env = self.whisper.build_processing_env(args)

        self.assertEqual(env["WHISPER_TARGETS"], '["clip.mp4"]')
        self.assertEqual(env["WHISPER_LANG"], "en")
        self.assertEqual(env["WHISPER_JOBS"], "3")
        self.assertEqual(env["WHISPER_OUTDIR"], "/tmp/out")
        self.assertEqual(env["WHISPER_BIBLE_REFERENCE_NORMALIZATION"], "1")
        self.assertEqual(env["WHISPER_BIBLE_REFERENCE_PHRASES"], "1")
        self.assertEqual(env["WHISPER_SPEECH_TRIM"], "0")
        self.assertEqual(env["WHISPER_REVIEW_POSTPROCESSING"], "1")
        self.assertEqual(env["WHISPER_SUBTITLE_STYLE"], "strict")
        self.assertEqual(env["WHISPER_GLOSSARY_FILES"], '["/tmp/glossary.txt"]')
        self.assertEqual(env["WHISPER_SUPPRESSION_FILES"], '["/tmp/suppress.txt"]')
        self.assertEqual(env["WHISPER_RECURSIVE"], "1")
        self.assertEqual(env["WHISPER_ASS"], "1")
        self.assertEqual(env["WHISPER_EMBED"], "1")
        self.assertEqual(env["WHISPER_EMBED_FILE_MODE"], "1")
        self.assertEqual(env["WHISPER_EMBED_FILE"], "captions.srt")
        self.assertEqual(env["WHISPER_IN_PLACE"], "1")
        self.assertEqual(env["WHISPER_BURN"], "0")
        self.assertEqual(env["WHISPER_BURN_VCODEC"], "libx264")
        self.assertEqual(env["WHISPER_FONT"], "Aptos")
        self.assertEqual(env["WHISPER_KARAOKE"], "1")

    def test_embedded_subtitle_plan_uses_mov_text_for_mp4_srt(self) -> None:
        output_path, codec = self.whisper.embedded_subtitle_plan(
            Path("clip.mp4"),
            Path("clip.srt"),
            Path("/tmp/out"),
        )

        self.assertEqual(output_path, Path("/tmp/out/clip_embedded.mp4"))
        self.assertEqual(codec, "mov_text")

    def test_embedded_subtitle_plan_falls_back_to_mkv_for_ass_in_mp4(self) -> None:
        output_path, codec = self.whisper.embedded_subtitle_plan(
            Path("clip.mp4"),
            Path("clip.ass"),
            Path("/tmp/out"),
        )

        self.assertEqual(output_path, Path("/tmp/out/clip_embedded.mkv"))
        self.assertEqual(codec, "ass")

    def test_resolve_embed_subtitle_path_prefers_single_matching_sidecar(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            subtitle = root / "clip.srt"
            media.write_text("video", encoding="utf-8")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

            resolved = self.whisper.resolve_embed_subtitle_path(media, "")

            self.assertEqual(resolved, subtitle)

    def test_resolve_embed_subtitle_path_rejects_ambiguous_sidecars(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            (root / "clip.srt").write_text("subtitles", encoding="utf-8")
            (root / "clip.ass").write_text("subtitles", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "multiple matching subtitle files"):
                self.whisper.resolve_embed_subtitle_path(media, "")

    def test_resolve_embed_subtitle_path_rejects_non_subtitle_extensions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            bogus = root / "clip.txt"
            media.write_text("video", encoding="utf-8")
            bogus.write_text("not a subtitle", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must be .srt or .ass"):
                self.whisper.resolve_embed_subtitle_path(media, str(bogus))
