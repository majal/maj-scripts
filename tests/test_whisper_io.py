from __future__ import annotations

import argparse
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
            paragraphs=False,
            speaker_labels=False,
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
        self.assertEqual(env["WHISPER_PARAGRAPHS"], "0")
        self.assertEqual(env["WHISPER_SPEAKER_LABELS"], "0")
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

    def test_transcript_short_option_matches_long_option(self) -> None:
        args = self.whisper.build_parser().parse_args(["clip.mp4", "-t"])

        self.assertTrue(args.transcript)

    def test_transcript_only_short_option_matches_long_option(self) -> None:
        args = self.whisper.build_parser().parse_args(["clip.mp4", "-T"])

        self.assertTrue(args.transcript_only)

    def test_speaker_label_flags_match_diarize_alias_and_imply_transcript(self) -> None:
        speaker_args = self.whisper.build_parser().parse_args(["clip.mp4", "--speaker-labels"])
        diarize_args = self.whisper.build_parser().parse_args(["clip.mp4", "--diarize"])

        self.assertTrue(speaker_args.speaker_labels)
        self.assertTrue(diarize_args.speaker_labels)
        self.assertEqual(self.whisper.build_processing_env(speaker_args)["WHISPER_TRANSCRIPT"], "1")
        self.assertEqual(self.whisper.build_processing_env(speaker_args)["WHISPER_SPEAKER_LABELS"], "1")

    def test_paragraphs_config_and_cli_flag_are_supported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            (root / self.whisper.PROJECT_CONFIG_FILENAME).write_text("paragraphs = true\n", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(self.whisper, "GLOBAL_CONFIG_PATH", root / "missing-global.toml"):
                    args = self.whisper.parse_args_with_config(self.whisper.build_parser(), ["clip.mp4"])
            finally:
                os.chdir(previous_cwd)

        self.assertTrue(args.paragraphs)

    def test_speaker_labels_config_is_supported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            (root / self.whisper.PROJECT_CONFIG_FILENAME).write_text("speaker_labels = true\n", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(self.whisper, "GLOBAL_CONFIG_PATH", root / "missing-global.toml"):
                    args = self.whisper.parse_args_with_config(self.whisper.build_parser(), ["clip.mp4"])
            finally:
                os.chdir(previous_cwd)

        self.assertTrue(args.speaker_labels)

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

    def test_existing_subtitle_can_supply_missing_transcript(self) -> None:
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
            self.assertTrue(self.whisper.output_plan_can_derive_transcript_from_subtitle(plan))
            self.assertTrue(self.whisper.output_plan_resume_from_subtitle(plan))

            transcript.write_text("Hello\n", encoding="utf-8")
            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

            self.assertFalse(self.whisper.output_plan_can_derive_transcript_from_subtitle(plan))
            self.assertTrue(self.whisper.output_plan_resume_from_subtitle(plan))

    def test_speaker_labels_do_not_derive_transcript_from_existing_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            subtitle = root / "clip.srt"
            media.write_text("video", encoding="utf-8")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_SPEAKER_LABELS": "1",
                "WHISPER_ASS": "0",
                "WHISPER_EMBED": "0",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
            }

            plan = self.whisper.transcription_output_plan(media, env, "faster-whisper")

        self.assertIsNone(plan["transcript_source_subtitle_path"])
        self.assertFalse(self.whisper.output_plan_can_derive_transcript_from_subtitle(plan))
        self.assertIn("label-speakers", plan["actions"])

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
        self.assertFalse(payload["speaker_labels"]["requested"])

    def test_dry_run_payload_reports_speaker_labels(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            args = self.whisper.parse_args_with_config(
                self.whisper.build_parser(),
                [
                    str(media),
                    "--plan",
                    "--backend=faster-whisper",
                    "--model=tiny",
                    "--state-dir",
                    str(root / "state"),
                    "--speaker-labels",
                    "--transcript-only",
                    "--no-speech-trim",
                ],
            )
            plan = self.whisper.build_runtime_plan(args)

            payload = self.whisper.build_dry_run_payload(args, plan)

        self.assertTrue(payload["speaker_labels"]["requested"])
        self.assertTrue(payload["actions"]["speaker_labels"])
        self.assertTrue(payload["defaults"]["transcript"])
        self.assertIn("label-speakers", payload["files"][0]["actions"])

    def test_speaker_label_packages_are_only_planned_when_requested(self) -> None:
        plan = argparse.Namespace(
            installed_packages=("webrtcvad",),
            selected_backend="faster-whisper",
            installed_backends=("faster-whisper",),
        )

        without_speakers = self.whisper.packages_to_install_now(
            plan,
            update=False,
            selected_backend_required=True,
            speaker_labels_required=False,
        )
        with_speakers = self.whisper.packages_to_install_now(
            plan,
            update=False,
            selected_backend_required=True,
            speaker_labels_required=True,
        )

        self.assertNotIn("speaker-labels", without_speakers)
        self.assertIn("speaker-labels", with_speakers)

    def test_speaker_label_cache_prefers_global_when_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            global_hub = root / "global-hub"
            state_dir = root / "state"
            snapshot = global_hub / self.whisper.SPEAKER_LABEL_REPO_CACHE_NAME / "snapshots" / "abc123"
            snapshot.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": str(global_hub)}, clear=False):
                scope, cache_dir = self.whisper.speaker_label_cache_choice(state_dir)
                self.assertEqual(scope, "global")
                self.assertEqual(cache_dir, global_hub)

                for child in snapshot.parent.iterdir():
                    child.rmdir()
                scope, cache_dir = self.whisper.speaker_label_cache_choice(state_dir)

        self.assertEqual(scope, "app")
        self.assertEqual(cache_dir, self.whisper.speaker_label_app_hub_cache_dir(state_dir))

    def test_deep_doctor_payload_imports_selected_backend_when_installed(self) -> None:
        plan = argparse.Namespace(
            selected_backend="faster-whisper",
            fallback_backend="none",
            installed_backends=("faster-whisper",),
            venv_python=Path("/fake/runtime/python"),
        )

        with (
            mock.patch.object(
                self.whisper,
                "runtime_import_probe",
                return_value={
                    "module": "faster_whisper",
                    "attempted": True,
                    "ok": True,
                    "returncode": 0,
                    "status": "exit code 0",
                    "stdout": "",
                    "stderr": "",
                },
            ) as probe,
            mock.patch.object(self.whisper, "runtime_has_speaker_labels", return_value=False),
        ):
            payload = self.whisper.deep_doctor_payload(plan)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["backends"][0]["label"], "faster-whisper")
        probe.assert_called_once_with(Path("/fake/runtime/python"), "faster_whisper")

    def test_deep_doctor_payload_marks_selected_backend_failure(self) -> None:
        plan = argparse.Namespace(
            selected_backend="mlx",
            fallback_backend="faster-whisper",
            installed_backends=("mlx",),
            venv_python=Path("/fake/runtime/python"),
        )

        with (
            mock.patch.object(
                self.whisper,
                "runtime_import_probe",
                return_value={
                    "module": "mlx_whisper",
                    "attempted": True,
                    "ok": False,
                    "returncode": -6,
                    "status": "signal 6",
                    "stdout": "",
                    "stderr": "",
                },
            ),
            mock.patch.object(self.whisper, "runtime_has_speaker_labels", return_value=False),
        ):
            payload = self.whisper.deep_doctor_payload(plan)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["backends"][0]["status"], "signal 6")
        self.assertFalse(payload["backends"][1]["attempted"])

    def test_mlx_exit_guidance_suggests_explicit_fallback(self) -> None:
        plan = argparse.Namespace(
            selected_backend="mlx",
            auto_backend=True,
            fallback_backend="faster-whisper",
        )

        with redirect_stderr(io.StringIO()) as stderr:
            self.whisper.print_backend_exit_guidance(plan, -6)

        output = stderr.getvalue()
        self.assertIn("signal 6", output)
        self.assertIn("--backend=faster-whisper", output)
        self.assertIn("auto fallback", output)

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

    def test_process_file_writes_missing_transcript_from_existing_srt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            subtitle = root / "clip.srt"
            transcript = root / "clip.txt"
            media.write_text("video", encoding="utf-8")
            subtitle.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello world\n\n",
                encoding="utf-8",
            )
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

            self.assertIn("Resumed", result)
            self.assertEqual(transcript.read_text(encoding="utf-8"), "Hello world\n")

    def test_transcript_from_existing_srt_can_format_paragraphs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            subtitle = root / "clip.srt"
            transcript = root / "clip.txt"
            media.write_text("video", encoding="utf-8")
            subtitle.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nFirst thought.\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\nSecond thought.\n\n",
                encoding="utf-8",
            )
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "0",
                "WHISPER_PARAGRAPHS": "1",
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

            self.assertEqual(transcript.read_text(encoding="utf-8"), "First thought.\n\nSecond thought.\n")

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
                "WHISPER_PARAGRAPHS": "0",
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
                "WHISPER_PARAGRAPHS": "0",
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

    def test_process_file_can_write_paragraph_transcript_from_segments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "1",
                "WHISPER_PARAGRAPHS": "1",
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
                {"start": 0.0, "end": 1.0, "text": "First paragraph.", "words": []},
                {"start": 3.0, "end": 4.0, "text": "Second paragraph.", "words": []},
            ]

            with (
                mock.patch.object(self.whisper, "run_faster_whisper", return_value=(segments, "en")),
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

            self.assertEqual((root / "clip.txt").read_text(encoding="utf-8"), "First paragraph.\n\nSecond paragraph.\n")

    def test_apply_speaker_turns_labels_segments_by_overlap(self) -> None:
        segments = [
            {"start": 0.0, "end": 1.0, "text": "Hello.", "words": []},
            {"start": 1.2, "end": 2.0, "text": "Hi.", "words": []},
            {"start": 2.1, "end": 3.0, "text": "Again.", "words": []},
        ]
        turns = [
            self.whisper.SpeakerTurn(0.0, 1.1, "SPEAKER_00"),
            self.whisper.SpeakerTurn(1.1, 2.1, "SPEAKER_01"),
            self.whisper.SpeakerTurn(2.1, 3.0, "SPEAKER_00"),
        ]

        labeled = self.whisper.apply_speaker_turns_to_segments(segments, turns)

        self.assertEqual([segment["speaker"] for segment in labeled], ["Speaker 1", "Speaker 2", "Speaker 1"])

    def test_process_file_can_write_speaker_labeled_paragraph_transcript(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            media.write_text("video", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": "",
                "WHISPER_MLX_OUTPUT_FORMAT": "auto",
                "WHISPER_TRANSCRIPT": "1",
                "WHISPER_TRANSCRIPT_ONLY": "1",
                "WHISPER_PARAGRAPHS": "1",
                "WHISPER_SPEAKER_LABELS": "1",
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
                "WHISPER_STATE_DIR": str(root / "state"),
            }
            segments = [
                {"start": 0.0, "end": 1.0, "text": "First thought.", "words": []},
                {"start": 1.2, "end": 2.0, "text": "Second thought.", "words": []},
                {"start": 3.8, "end": 4.4, "text": "Reply.", "words": []},
            ]
            labeled_segments = [
                {**segments[0], "speaker": "Speaker 1"},
                {**segments[1], "speaker": "Speaker 1"},
                {**segments[2], "speaker": "Speaker 2"},
            ]

            with (
                mock.patch.object(self.whisper, "run_faster_whisper", return_value=(segments, "en")),
                mock.patch.object(self.whisper, "run_speaker_labeling", return_value=labeled_segments),
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

            self.assertEqual(
                (root / "clip.txt").read_text(encoding="utf-8"),
                "Speaker 1: First thought. Second thought.\n\nSpeaker 2: Reply.\n",
            )

    def test_ensure_system_prereqs_requires_ffmpeg_for_embed(self) -> None:
        args = argparse.Namespace(
            embed=True,
            embed_file=None,
            burn=False,
            backend="auto",
            mlx_word_timestamps="auto",
            mlx_output_format="auto",
            mlx_model_default="wrapper",
            transcript=False,
            transcript_only=False,
            paragraphs=False,
            speaker_labels=False,
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

    def test_clean_speaker_labels_removes_only_optional_runtime_and_app_cache(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_dir = root / "state"
            cache_root = self.whisper.speaker_label_app_cache_root(state_dir)
            cache_root.mkdir(parents=True)
            (cache_root / "model.bin").write_text("cache", encoding="utf-8")
            python_bin = state_dir / "venv" / "bin" / "python"
            python_bin.parent.mkdir(parents=True)
            python_bin.write_text("python", encoding="utf-8")
            plan = argparse.Namespace(state_dir=state_dir, venv_python=python_bin)

            with (
                mock.patch.object(self.whisper, "runtime_has_speaker_labels", return_value=True),
                mock.patch.object(self.whisper, "uninstall_packages") as uninstall,
                redirect_stderr(io.StringIO()),
                redirect_stdout(io.StringIO()),
            ):
                self.whisper.clean_speaker_labels(plan, assume_yes=True)

            uninstall.assert_called_once()
            self.assertFalse(cache_root.exists())

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
