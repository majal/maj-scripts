from __future__ import annotations

import argparse
import io
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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
            transcript=False,
            transcript_only=False,
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
        self.assertEqual(env["WHISPER_TRANSCRIPT"], "0")
        self.assertEqual(env["WHISPER_TRANSCRIPT_ONLY"], "0")
        self.assertEqual(env["WHISPER_ASS"], "1")
        self.assertEqual(env["WHISPER_EMBED"], "1")
        self.assertEqual(env["WHISPER_EMBED_FILE_MODE"], "1")
        self.assertEqual(env["WHISPER_EMBED_FILE"], "captions.srt")
        self.assertEqual(env["WHISPER_IN_PLACE"], "1")
        self.assertEqual(env["WHISPER_BURN"], "0")
        self.assertEqual(env["WHISPER_BURN_VCODEC"], "libx264")
        self.assertEqual(env["WHISPER_FONT"], "Aptos")
        self.assertEqual(env["WHISPER_KARAOKE"], "1")
        self.assertEqual(env["WHISPER_FORCE"], "0")

    def test_build_processing_env_enables_transcript_only_without_video_outputs(self) -> None:
        args = self.whisper.build_parser().parse_args(
            ["clip.mp4", "--transcript-only", "--embed", "--burn", "--ass", "--karaoke"]
        )

        env = self.whisper.build_processing_env(args)

        self.assertEqual(env["WHISPER_TRANSCRIPT"], "0")
        self.assertEqual(env["WHISPER_TRANSCRIPT_ONLY"], "1")
        self.assertEqual(env["WHISPER_ASS"], "0")
        self.assertEqual(env["WHISPER_EMBED"], "0")
        self.assertEqual(env["WHISPER_BURN"], "0")
        self.assertEqual(env["WHISPER_KARAOKE"], "0")

    def test_project_config_applies_defaults_but_cli_wins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_config = root / self.whisper.PROJECT_CONFIG_FILENAME
            global_config = root / "global-config.toml"
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            global_config.write_text(
                """
                lang = "tl"
                glossary = ["global-glossary.txt"]
                speech_trim = false
                """,
                encoding="utf-8",
            )
            project_config.write_text(
                """
                [defaults]
                subtitle-style = "strict"
                extra_glossary = ["project-glossary.txt"]
                suppress_phrases = ["project-suppress.txt"]
                jobs = 2
                """,
                encoding="utf-8",
            )
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(self.whisper, "GLOBAL_CONFIG_PATH", global_config):
                    args = self.whisper.parse_args_with_config(
                        self.whisper.build_parser(),
                        ["clip.mp4", "--lang=en"],
                    )
                    cli_args = self.whisper.parse_args_with_config(
                        self.whisper.build_parser(),
                        ["clip.mp4", "--glossary=cli-glossary.txt"],
                    )
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(args.lang, "en")
        self.assertEqual(args.subtitle_style, "strict")
        self.assertEqual(args.glossary, ["global-glossary.txt", "project-glossary.txt"])
        self.assertEqual(args.suppress_phrases, ["project-suppress.txt"])
        self.assertFalse(args.speech_trim)
        self.assertEqual(args.jobs, 2)
        self.assertEqual(cli_args.glossary, ["cli-glossary.txt"])

    def test_output_plan_detects_existing_outputs_and_resume_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "0",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "1",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
            }

            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")
            self.assertFalse(self.whisper.output_plan_complete(plan))
            self.assertFalse(self.whisper.output_plan_resume_from_subtitle(plan))

            subtitle = root / "clip.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

            self.assertFalse(self.whisper.output_plan_complete(plan))
            self.assertTrue(self.whisper.output_plan_resume_from_subtitle(plan))

            embedded = root / "clip_embedded.mp4"
            embedded.write_text("embedded", encoding="utf-8")
            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

            self.assertTrue(self.whisper.output_plan_complete(plan))

    def test_transcript_output_plan_adds_text_without_dropping_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "0",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
            }

            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

        self.assertEqual(plan["text_path"], root / "clip.txt")
        self.assertEqual(plan["subtitle_path"], root / "clip.srt")
        self.assertEqual(plan["expected_outputs"], (root / "clip.txt", root / "clip.srt"))
        self.assertIn("write-transcript", plan["actions"])
        self.assertIn("write-srt", plan["actions"])

    def test_transcript_only_output_plan_skips_subtitle_and_video_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "0",
                "WHISPER_TRANSCRIPT_ONLY": "1",
                "WHISPER_ASS": "1",
                "WHISPER_EMBED": "1",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "1",
            }

            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

        self.assertEqual(plan["text_path"], root / "clip.txt")
        self.assertIsNone(plan["subtitle_path"])
        self.assertIsNone(plan["embedded_path"])
        self.assertIsNone(plan["burn_path"])
        self.assertEqual(plan["expected_outputs"], (root / "clip.txt",))
        self.assertIn("transcript-only", plan["actions"])

    def test_resume_from_subtitle_requires_existing_transcript_when_requested(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            subtitle = root / "clip.srt"
            transcript = root / "clip.txt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "1",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
            }

            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")
            self.assertFalse(self.whisper.output_plan_resume_from_subtitle(plan))

            transcript.write_text("Hello\n", encoding="utf-8")
            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

            self.assertTrue(self.whisper.output_plan_resume_from_subtitle(plan))

    def test_dry_run_payload_reports_outputs_and_ffmpeg_need(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(self.whisper, "GLOBAL_CONFIG_PATH", root / "missing-global.toml"):
                    args = self.whisper.parse_args_with_config(
                        self.whisper.build_parser(),
                        [
                            str(media),
                            "--plan",
                            "--backend=faster-whisper",
                            "--model=tiny",
                            "--state-dir",
                            str(root / "state"),
                            "--embed",
                            "--no-speech-trim",
                        ],
                    )
                    plan = self.whisper.build_runtime_plan(args)
                    payload = self.whisper.build_dry_run_payload(args, plan)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(payload["mode"], "plan")
        self.assertTrue(payload["actions"]["embed"])
        self.assertTrue(payload["ffmpeg"]["required"])
        self.assertEqual(payload["inputs"]["files_discovered"], 1)
        self.assertEqual(payload["files"][0]["status"], "will transcribe")
        self.assertIn("clip.srt", payload["files"][0]["subtitle_path"])
        self.assertIn("clip_embedded.mp4", payload["files"][0]["embedded_path"])

    def test_process_file_skips_when_subtitle_already_exists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            subtitle = root / "clip.srt"
            media.write_text("video", encoding="utf-8")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "0",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "0",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
                "WHISPER_FORCE": "0",
                "WHISPER_LANG": "en",
            }

            with (
                mock.patch.object(self.whisper, "run_faster_whisper", side_effect=AssertionError("should not transcribe")),
                redirect_stderr(io.StringIO()),
            ):
                result = self.whisper.process_file(
                    media,
                    env,
                    "faster-whisper",
                    file_index=1,
                    total_files=1,
                    inline_progress=False,
                    compact_status=True,
                    show_progress=False,
                    show_stage_messages=False,
                )

        self.assertIn("Skipped", result)

    def test_process_file_writes_transcript_and_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "0",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
                "WHISPER_FORCE": "0",
                "WHISPER_LANG": "en",
                "WHISPER_MODEL": "tiny",
                "WHISPER_BACKEND": "faster-whisper",
                "WHISPER_FALLBACK_BACKEND": "none",
                "WHISPER_DEVICE": "cpu",
                "WHISPER_COMPUTE_TYPE": "int8",
                "WHISPER_FALLBACK_DEVICE": "none",
                "WHISPER_FALLBACK_COMPUTE_TYPE": "none",
                "WHISPER_BIBLE_REFERENCE_NORMALIZATION": "1",
                "WHISPER_BIBLE_REFERENCE_PHRASES": "0",
                "WHISPER_SPEECH_TRIM": "0",
                "WHISPER_REVIEW_POSTPROCESSING": "0",
                "WHISPER_SUBTITLE_STYLE": "balanced",
                "WHISPER_GLOSSARY_FILES": "[]",
                "WHISPER_SUPPRESSION_FILES": "[]",
                "WHISPER_FONT": "Arial",
                "WHISPER_KARAOKE": "0",
            }
            segments = [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "psalm 83 18 jehovah",
                    "words": [
                        {"start": 0.0, "end": 0.2, "word": "psalm"},
                        {"start": 0.2, "end": 0.4, "word": "83"},
                        {"start": 0.4, "end": 0.6, "word": "18"},
                        {"start": 0.6, "end": 1.0, "word": "jehovah"},
                    ],
                }
            ]

            with (
                mock.patch.object(self.whisper, "run_faster_whisper", return_value=(segments, "en")),
                redirect_stderr(io.StringIO()),
            ):
                result = self.whisper.process_file(
                    media,
                    env,
                    "faster-whisper",
                    file_index=1,
                    total_files=1,
                    inline_progress=False,
                    compact_status=True,
                    show_progress=False,
                    show_stage_messages=False,
                )

            transcript = (root / "clip.txt").read_text(encoding="utf-8")
            subtitle = (root / "clip.srt").read_text(encoding="utf-8")

        self.assertIn("Done", result)
        self.assertIn("Psalm 83:18 Jehovah", transcript)
        self.assertIn("Psalm 83:18 Jehovah", subtitle)

    def test_process_file_transcript_only_skips_subtitle_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "0",
                "WHISPER_TRANSCRIPT_ONLY": "1",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "0",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
                "WHISPER_FORCE": "0",
                "WHISPER_LANG": "en",
                "WHISPER_MODEL": "tiny",
                "WHISPER_BACKEND": "faster-whisper",
                "WHISPER_FALLBACK_BACKEND": "none",
                "WHISPER_DEVICE": "cpu",
                "WHISPER_COMPUTE_TYPE": "int8",
                "WHISPER_FALLBACK_DEVICE": "none",
                "WHISPER_FALLBACK_COMPUTE_TYPE": "none",
                "WHISPER_BIBLE_REFERENCE_NORMALIZATION": "1",
                "WHISPER_BIBLE_REFERENCE_PHRASES": "0",
                "WHISPER_SPEECH_TRIM": "0",
                "WHISPER_REVIEW_POSTPROCESSING": "0",
                "WHISPER_SUBTITLE_STYLE": "balanced",
                "WHISPER_GLOSSARY_FILES": "[]",
                "WHISPER_SUPPRESSION_FILES": "[]",
                "WHISPER_FONT": "Arial",
                "WHISPER_KARAOKE": "0",
            }

            with (
                mock.patch.object(
                    self.whisper,
                    "run_faster_whisper",
                    return_value=([{"start": 0.0, "end": 1.0, "text": "hello transcript", "words": []}], "en"),
                ),
                redirect_stderr(io.StringIO()),
            ):
                self.whisper.process_file(
                    media,
                    env,
                    "faster-whisper",
                    file_index=1,
                    total_files=1,
                    inline_progress=False,
                    compact_status=True,
                    show_progress=False,
                    show_stage_messages=False,
                )

            self.assertTrue((root / "clip.txt").is_file())
            self.assertFalse((root / "clip.srt").exists())

    def test_ensure_system_prereqs_requires_ffmpeg_for_embed(self) -> None:
        args = argparse.Namespace(
            embed=True,
            embed_file=None,
            burn=False,
            backend="auto",
            mlx_word_timestamps="auto",
            mlx_output_format="auto",
            mlx_model_default="wrapper",
            in_place=False,
            burn_vcodec="auto",
        )

        with (
            mock.patch.object(self.whisper.shutil, "which", return_value=None),
            mock.patch.object(self.whisper, "print_install_help"),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            with self.assertRaises(SystemExit) as raised:
                self.whisper.ensure_system_prereqs(args, "linux", "apt-get")

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("ffmpeg is required for --embed/--embed-file", stderr.getvalue())

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
