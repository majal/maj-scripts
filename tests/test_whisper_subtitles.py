from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support import load_script_module


class WhisperSubtitleOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.whisper = load_script_module("whisper")

    def test_write_srt_formats_cues_and_timestamps(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "clip.srt"
            self.whisper.write_srt(
                output,
                [{"start": 0.0, "end": 1.234, "text": "Hello world", "words": []}],
            )

            text = output.read_text(encoding="utf-8")

        self.assertIn("1\n00:00:00,000 --> 00:00:01,234\nHello world\n", text)

    def test_write_ass_formats_dialogue_and_karaoke_tags(self) -> None:
        segment = {
            "start": 0.0,
            "end": 1.25,
            "text": "Hello world",
            "words": [
                {"start": 0.0, "end": 0.5, "word": "Hello"},
                {"start": 0.5, "end": 1.25, "word": "world"},
            ],
        }
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "clip.ass"
            self.whisper.write_ass(output, [segment], "Aptos", karaoke=True)

            text = output.read_text(encoding="utf-8")

        self.assertIn("[Script Info]", text)
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:01.25", text)
        self.assertIn(r"{\k50}Hello", text)
        self.assertIn(r"{\k75}world", text)

    def test_dense_cues_are_split_for_readability(self) -> None:
        cue = self.whisper.SubtitleCue(
            0.0,
            2.0,
            "one two three four five six seven eight nine ten eleven twelve thirteen".split(),
        )

        cues = self.whisper.split_dense_subtitle_cue(cue, style=self.whisper.SUBTITLE_STYLE_PRESETS["balanced"])

        self.assertGreater(len(cues), 1)
        self.assertTrue(all(split.end > split.start for split in cues))

    def test_speech_trim_moves_edges_to_detected_speech(self) -> None:
        cue = self.whisper.SubtitleCue(0.0, 5.0, ["long", "lead"])

        trimmed = self.whisper.subtitle_cue_apply_speech_trim(cue, [(1.0, 2.0)])

        self.assertAlmostEqual(trimmed.start, 0.94, places=2)
        self.assertAlmostEqual(trimmed.end, 2.12, places=2)
